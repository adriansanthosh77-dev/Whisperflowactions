"""
whatsapp_executor.py — Native Obscura WhatsApp Executor.
"""

import time
import logging
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

WHATSAPP_URL = "https://web.whatsapp.com"

class WhatsAppExecutor(BaseExecutor):

    def send_message(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        recipient = intent.target
        message = intent.data.get("message", "")
        draft_only = bool(intent.data.get("draft_only"))

        if not recipient:
            return False, "No recipient specified."
        if not message:
            return False, "No message content."

        try:
            self.navigate(WHATSAPP_URL)
            self.wait_for_ready(timeout=12) # WhatsApp can be slow to load
            
            # Simple adaptive attempt via CDP
            # 1. Search for recipient
            self.fill_resilient(None, recipient, labels=["Search"])
            time.sleep(1)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 13}) # Enter
            self._cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})
            time.sleep(1)
            
            # 2. Type message
            self.fill_resilient(None, message, labels=["Type a message"])
            time.sleep(0.5)
            if draft_only:
                return True, f"WhatsApp draft prepared for {recipient}."

            self._cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "windowsVirtualKeyCode": 13}) # Enter
            self._cdp.send("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})
            
            return True, f"Message sent to {recipient} on WhatsApp."
        except Exception as e:
            return False, f"WhatsApp send failed: {str(e)[:80]}"
