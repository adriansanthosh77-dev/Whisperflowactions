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

        if not recipient:
            return False, "No recipient specified."
        if not message:
            return False, "No message content."

        try:
            self.navigate(WHATSAPP_URL)
            time.sleep(5) # Wait for load
            
            # Simple adaptive attempt via CDP
            # 1. Search for recipient
            self.fill_resilient(None, recipient, labels=["Search"])
            time.sleep(1)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": "\r"}) # Press Enter
            time.sleep(1)
            
            # 2. Type message
            self.fill_resilient(None, message, labels=["Type a message"])
            time.sleep(0.5)
            self._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": "\r"}) # Press Enter
            
            return True, f"Message sent to {recipient} on WhatsApp."
        except Exception as e:
            return False, f"WhatsApp send failed: {str(e)[:80]}"
