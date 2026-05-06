"""
action_router.py — Routes IntentResult to the correct executor.

Validates required params before handing off.
Returns (success: bool, message: str).
"""

import logging
from models.intent_schema import IntentResult, Context
from executors.whatsapp_executor import WhatsAppExecutor
from executors.gmail_executor import GmailExecutor
from executors.browser_executor import BrowserExecutor

logger = logging.getLogger(__name__)

# Singleton executors — share one Playwright browser instance
_whatsapp = WhatsAppExecutor()
_gmail = GmailExecutor()
_browser = BrowserExecutor()


# Maps (intent, app) → callable
ROUTE_TABLE = {
    ("send_message", "whatsapp"): (_whatsapp, "send_message"),
    ("send_message", "gmail"):    (_gmail,    "send_email"),
    ("summarize",    "browser"):  (_browser,  "summarize_page"),
    ("summarize",    "gmail"):    (_gmail,    "summarize_thread"),
    ("reply_professionally", "gmail"): (_gmail, "reply_professionally"),
    ("create_task",  "notion"):   (_browser,  "create_notion_task"),
    ("open_app",     "whatsapp"): (_browser,  "open_url"),
    ("open_app",     "gmail"):    (_browser,  "open_url"),
    ("open_app",     "notion"):   (_browser,  "open_url"),
    ("browser_action", "browser"): (_browser, "adaptive_browser_task"),
}

APP_URLS = {
    "whatsapp": "https://web.whatsapp.com",
    "gmail":    "https://mail.google.com",
    "notion":   "https://www.notion.so",
}

# Required params per intent
REQUIRED_PARAMS = {
    "send_message":        ["target"],
    "summarize":           [],
    "reply_professionally": [],
    "create_task":         ["target"],  # target = task title
    "open_app":            ["app"],
    "browser_action":      [],
}


class ActionRouter:
    def route(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """
        Dispatch intent to executor.
        Returns (success, human-readable result message).
        """
        logger.info(f"Routing: intent={intent.intent}, app={intent.app}")

        # Unknown intent
        if intent.intent == "unknown" or intent.confidence < 0.5:
            return False, f"I couldn't understand that command. (confidence={intent.confidence:.0%})"

        # Validate required params
        missing = self._check_params(intent)
        if missing:
            return False, f"Missing required info: {', '.join(missing)}"

        # Inject URL for open_app
        if intent.intent == "open_app":
            intent.data["url"] = APP_URLS.get(intent.app, "")
            if not intent.data["url"]:
                return False, f"Unknown app: {intent.app}"

        # Look up route
        route_key = (intent.intent, intent.app)
        if route_key not in ROUTE_TABLE:
            # Fallback: try with browser
            route_key = (intent.intent, "browser")
            if route_key not in ROUTE_TABLE:
                return False, f"No executor for: {intent.intent} on {intent.app}"

        executor, method_name = ROUTE_TABLE[route_key]

        try:
            result = getattr(executor, method_name)(intent, context)
            return result
        except Exception as e:
            logger.exception(f"Executor failed: {e}")
            return False, f"Action failed: {str(e)[:100]}"

    def _check_params(self, intent: IntentResult) -> list[str]:
        required = REQUIRED_PARAMS.get(intent.intent, [])
        missing = []
        for param in required:
            if param == "target" and not intent.target:
                missing.append("target/recipient")
            elif param == "app" and not intent.app:
                missing.append("app name")
        return missing
