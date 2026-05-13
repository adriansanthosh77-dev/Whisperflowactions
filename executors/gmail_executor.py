"""
gmail_executor.py — Native Obscura Gmail Executor.
"""

import time
import logging
import os
import requests
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

GMAIL_URL = "https://mail.google.com"

class GmailExecutor(BaseExecutor):

    def send_email(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        recipient = intent.target
        message = intent.data.get("message", "")
        draft_only = bool(intent.data.get("draft_only"))

        if not recipient:
            return False, "No recipient specified."

        try:
            self.navigate(GMAIL_URL)
            self.wait_for_ready(timeout=10)
            
            # Simple adaptive attempt via CDP
            self.click_resilient(None, labels=["Compose"])
            time.sleep(1)
            self.fill_resilient(None, recipient, labels=["To", "Recipients"])
            time.sleep(0.5)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": "\t"}) # Tab to subject
            time.sleep(0.2)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": "\t"}) # Tab to body
            time.sleep(0.2)
            self.fill_resilient(None, message, labels=["Message Body"])
            time.sleep(0.5)
            
            if draft_only:
                return True, f"Email draft prepared for {recipient}."

            # Ctrl+Enter to send (correct CDP key events)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 17}) # Ctrl down
            self._cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 13}) # Enter down
            self._cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13}) # Enter up
            self._cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 17}) # Ctrl up

            return True, f"Email sent to {recipient}."
        except Exception as e:
            return False, f"Gmail send failed: {str(e)[:80]}"

    def summarize_thread(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        try:
            self._ensure_browser()
            text = self._cdp.evaluate("document.body.innerText")[:6000]
            summary = self._gpt_summarize(text)
            return True, f"Summary:\n{summary}"
        except Exception as e:
            return False, f"Summarize failed: {str(e)[:80]}"

    def _gpt_summarize(self, text: str) -> str:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Summarize this email thread in 3-5 bullet points. Be concise."},
                        {"role": "user", "content": text},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=20
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()
        except Exception:
            return "Summary unavailable (Ollama offline)."
