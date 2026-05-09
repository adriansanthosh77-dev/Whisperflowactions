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

        if not recipient:
            return False, "No recipient specified."

        try:
            self.navigate(GMAIL_URL)
            time.sleep(5)
            
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
            
            # Ctrl+Enter to send
            self._cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 17, "modifiers": 2}) # Ctrl
            self._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": "\r", "modifiers": 2}) # Enter
            self._cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 17})
            
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
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": "Summarize this email thread in 3-5 bullet points. Be concise."},
                {"role": "user", "content": text},
            ],
            "max_tokens": 300,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
