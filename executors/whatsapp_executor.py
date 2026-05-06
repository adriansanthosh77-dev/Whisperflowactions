"""
whatsapp_executor.py — Send WhatsApp messages via WhatsApp Web.

Selectors are based on WhatsApp Web's current DOM (May 2025).
Uses aria-labels and data-testids which are more stable than class names.
"""

import time
import logging
from playwright.sync_api import Page, TimeoutError as PWTimeout
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com"

# First-choice selectors. Executors now fall back to role/text, DOM boxes,
# mouse clicks, screenshots, and feedback hints when these break.
SEL_SEARCH_BOX   = 'div[contenteditable="true"][data-tab="3"]'
SEL_SEARCH_CLEAR = 'button[aria-label="Cancel search"]'
SEL_CHAT_RESULT  = 'span[title="{name}"]'               # formatted at runtime
SEL_MSG_BOX      = 'div[contenteditable="true"][data-tab="10"]'
SEL_SEND_BTN     = 'button[data-testid="send"]'
SEL_QR_CODE      = 'canvas[aria-label="Scan this QR code to link a device"]'
SEL_MAIN_PANEL   = 'div[id="main"]'


class WhatsAppExecutor(BaseExecutor):

    def send_message(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        recipient = intent.target
        message = intent.data.get("message", "")

        if not recipient:
            return False, "No recipient specified for WhatsApp message."
        if not message:
            return False, "No message content specified."

        def _execute():
            page = self.get_or_create_page("web.whatsapp.com")
            self._ensure_loaded(page)
            self._open_chat(page, recipient)
            self._type_and_send(page, message)

        try:
            self.with_retry(_execute)
            logger.info(f"WhatsApp message sent to '{recipient}'")
            return True, f"Message sent to {recipient} on WhatsApp."
        except Exception as e:
            logger.error(f"WhatsApp send failed: {e}")
            return False, f"Failed to send WhatsApp message: {str(e)[:80]}"

    def _ensure_loaded(self, page: Page):
        """Navigate to WhatsApp Web and wait for it to be ready."""
        if "web.whatsapp.com" not in page.url:
            page.goto(WHATSAPP_URL, wait_until="networkidle", timeout=30000)

        # Check if QR code login required
        try:
            page.wait_for_selector(SEL_QR_CODE, timeout=3000)
            raise RuntimeError(
                "WhatsApp Web requires QR scan. Please open WhatsApp Web manually and scan."
            )
        except PWTimeout:
            pass  # QR not shown → already logged in

        # Wait for either a known search box or enough DOM to reason from.
        try:
            page.wait_for_selector(SEL_SEARCH_BOX, timeout=12000)
        except PWTimeout:
            match = self.find_dom_match(page, ["search", "search input", "start new chat"])
            if not match:
                shot = self.capture_screenshot(page, "whatsapp_not_ready")
                raise RuntimeError(f"WhatsApp not ready or not logged in. screenshot={shot}")
        time.sleep(0.5)  # brief settle

    def _open_chat(self, page: Page, name: str):
        """Search for contact and open their chat."""
        self.click_resilient(
            page,
            selectors=[
                SEL_SEARCH_BOX,
                'div[role="textbox"][contenteditable="true"]',
                'div[aria-label*="Search"]',
            ],
            labels=["Search", "Search input textbox", "Search or start new chat"],
        )
        time.sleep(0.2)

        self.fill_resilient(
            page,
            name,
            selectors=[
                SEL_SEARCH_BOX,
                'div[role="textbox"][contenteditable="true"]',
                'div[aria-label*="Search"]',
            ],
            labels=["Search", "Search input textbox", "Search or start new chat"],
        )
        time.sleep(1.0)  # wait for search results to render

        result_sel = SEL_CHAT_RESULT.format(name=name)
        self.click_resilient(
            page,
            selectors=[result_sel, f'span[title*="{name}"]'],
            labels=[name],
            timeout=5000,
        )

        # Wait for message box to appear (chat opened)
        try:
            page.wait_for_selector(SEL_MSG_BOX, timeout=8000)
        except PWTimeout:
            match = self.find_dom_match(page, ["message", "type a message"], tags=["div"])
            if not match:
                shot = self.capture_screenshot(page, "whatsapp_chat_not_open")
                raise RuntimeError(f"Could not confirm WhatsApp chat opened. screenshot={shot}")
        time.sleep(0.3)

    def _type_and_send(self, page: Page, message: str):
        """Type message and click send."""
        self.fill_resilient(
            page,
            message,
            selectors=[
                SEL_MSG_BOX,
                'div[aria-label="Type a message"]',
                'div[role="textbox"][contenteditable="true"]',
            ],
            labels=["Type a message", "Message"],
            press_ctrl_a=False,
        )
        time.sleep(0.1)

        # Click send button
        try:
            self.click_resilient(
                page,
                selectors=[SEL_SEND_BTN, 'button[aria-label="Send"]', 'span[data-icon="send"]'],
                labels=["Send"],
                timeout=3000,
            )
        except Exception:
            # Fallback: press Enter
            page.keyboard.press("Enter")

        time.sleep(0.5)  # confirm message appears in chat
