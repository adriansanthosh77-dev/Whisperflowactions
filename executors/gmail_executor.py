"""
gmail_executor.py — Gmail actions via Playwright.

Supported: send_email, summarize_thread, reply_professionally
"""

import time
import logging
import os
from openai import OpenAI
from playwright.sync_api import Page, TimeoutError as PWTimeout
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)
client = None


def get_openai_client() -> OpenAI:
    global client
    if client is None:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return client

GMAIL_URL = "https://mail.google.com"

SEL_COMPOSE_BTN  = 'div[gh="cm"]'
SEL_TO_FIELD     = 'input[name="to"]'
SEL_SUBJECT      = 'input[name="subjectbox"]'
SEL_BODY         = 'div[aria-label="Message Body"]'
SEL_SEND         = 'div[data-tooltip="Send ‪(Ctrl-Enter)‬"]'
SEL_EMAIL_BODY   = 'div.a3s.aiL'  # email body in open thread


class GmailExecutor(BaseExecutor):

    def send_email(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        recipient = intent.target
        message = intent.data.get("message", "")

        def _execute():
            page = self.get_or_create_page("mail.google.com")
            self._ensure_loaded(page)
            self._compose_and_send(page, recipient, "", message)

        try:
            self.with_retry(_execute)
            return True, f"Email sent to {recipient}."
        except Exception as e:
            return False, f"Gmail send failed: {str(e)[:80]}"

    def summarize_thread(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Extract email body text and summarize with GPT."""
        def _execute():
            page = self.get_or_create_page("mail.google.com")
            self._ensure_loaded(page)
            return self._extract_thread_text(page)

        try:
            thread_text = self.with_retry(_execute)
            summary = self._gpt_summarize(thread_text)
            return True, f"Summary:\n{summary}"
        except Exception as e:
            return False, f"Summarize failed: {str(e)[:80]}"

    def reply_professionally(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Generate and pre-fill a professional reply draft."""
        def _execute():
            page = self.get_or_create_page("mail.google.com")
            self._ensure_loaded(page)
            thread_text = self._extract_thread_text(page)
            reply_text = self._gpt_professional_reply(thread_text, intent.data)
            self._open_reply_draft(page, reply_text)
            return reply_text

        try:
            reply = self.with_retry(_execute)
            return True, f"Professional reply drafted. Please review and send."
        except Exception as e:
            return False, f"Reply generation failed: {str(e)[:80]}"

    # ── Private helpers ────────────────────────────────────────────────────

    def _ensure_loaded(self, page: Page):
        if "mail.google.com" not in page.url:
            page.goto(GMAIL_URL, wait_until="networkidle", timeout=30000)
        try:
            page.wait_for_selector(SEL_COMPOSE_BTN, timeout=15000)
        except PWTimeout:
            match = self.find_dom_match(page, ["compose", "mail"], tags=["div", "button"])
            if not match:
                shot = self.capture_screenshot(page, "gmail_not_ready")
                raise RuntimeError(f"Gmail not loaded or not logged in. screenshot={shot}")

    def _compose_and_send(self, page: Page, to: str, subject: str, body: str):
        self.click_resilient(
            page,
            selectors=[SEL_COMPOSE_BTN, 'div[role="button"][gh="cm"]'],
            labels=["Compose"],
        )
        time.sleep(0.5)

        self.fill_resilient(
            page,
            to,
            selectors=[SEL_TO_FIELD, 'textarea[name="to"]', 'input[aria-label*="To"]'],
            labels=["To", "Recipients"],
        )
        page.keyboard.press("Tab")
        if subject:
            self.fill_resilient(
                page,
                subject,
                selectors=[SEL_SUBJECT, 'input[aria-label*="Subject"]'],
                labels=["Subject"],
            )
            page.keyboard.press("Tab")

        self.fill_resilient(
            page,
            body,
            selectors=[
                SEL_BODY,
                'div[role="textbox"][aria-label*="Message Body"]',
                'div[contenteditable="true"][aria-label*="Message"]',
            ],
            labels=["Message Body", "Body"],
            press_ctrl_a=False,
        )
        time.sleep(0.3)

        self.click_resilient(
            page,
            selectors=[SEL_SEND, 'div[role="button"][aria-label*="Send"]'],
            labels=["Send"],
        )
        time.sleep(0.5)

    def _extract_thread_text(self, page: Page) -> str:
        try:
            bodies = page.query_selector_all(SEL_EMAIL_BODY)
            texts = [b.inner_text() for b in bodies if b.inner_text().strip()]
            combined = "\n\n---\n\n".join(texts)
            return combined[:6000]  # cap for GPT context
        except Exception:
            # Fallback: use selected_text or page text
            return page.inner_text("body")[:3000]

    def _open_reply_draft(self, page: Page, reply_text: str):
        """Click Reply button and pre-fill with generated text."""
        try:
            self.click_resilient(
                page,
                selectors=['button[data-tooltip*="Reply"]', 'div[role="button"][aria-label*="Reply"]'],
                labels=["Reply"],
                timeout=5000,
            )
            time.sleep(0.5)
            self.fill_resilient(
                page,
                reply_text,
                selectors=[
                    SEL_BODY,
                    'div[role="textbox"][aria-label*="Message Body"]',
                    'div[contenteditable="true"][aria-label*="Message"]',
                ],
                labels=["Message Body", "Body"],
                press_ctrl_a=False,
            )
        except Exception as e:
            logger.warning(f"Could not open reply draft: {e}")

    def _gpt_summarize(self, text: str) -> str:
        resp = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Summarize this email thread in 3-5 bullet points. Be concise."},
                {"role": "user", "content": text},
            ],
            max_tokens=300,
        )
        return resp.choices[0].message.content.strip()

    def _gpt_professional_reply(self, thread_text: str, data: dict) -> str:
        tone = data.get("tone", "formal")
        key_points = data.get("key_points", [])
        points_str = "\n".join(f"- {p}" for p in key_points) if key_points else "no specific points given"

        resp = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    f"Write a {tone} professional email reply to this thread. "
                    f"Address these key points if relevant: {points_str}. "
                    "Output only the email body text, no subject line."
                )},
                {"role": "user", "content": thread_text},
            ],
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
