"""
action_router.py — Routes IntentResult to the correct executor.

Handles any app or website:
  - Known apps (whatsapp, gmail, notion) → dedicated executors
  - Any other app/site ("YouTube", "Reddit", "bank") → URL resolved then browser_action
  - browser_action on any app → adaptive_browser_task (LLM-driven)

Returns (success: bool, message: str).
"""

import re
import os
import logging
import requests as http_requests
from urllib.parse import quote_plus
from models.intent_schema import IntentResult, Context
from executors.whatsapp_executor import WhatsAppExecutor
from executors.gmail_executor import GmailExecutor
from executors.browser_executor import BrowserExecutor
from executors.base_executor import BaseExecutor
from executors.pc_executor import PCExecutor
from executors.chat_executor import ChatExecutor

logger = logging.getLogger(__name__)

# ── Singleton executors — share one Playwright browser instance ──────────
_whatsapp = WhatsAppExecutor()
_gmail    = GmailExecutor()
browser_executor = BrowserExecutor()
pc_executor = PCExecutor()
chat_executor = ChatExecutor()

# ── Hard-wired route table for dedicated executors ───────────────────────
ROUTE_TABLE = {
    ("send_message",        "whatsapp"): (_whatsapp, "send_message"),
    ("send_message",        "gmail"):    (_gmail,    "send_email"),
    ("summarize",           "gmail"):    (_gmail,    "summarize_thread"),
    ("reply_professionally","gmail"):    (_gmail,    "reply_professionally"),
    ("create_task",         "notion"):   (browser_executor,  "create_notion_task"),
}

# ── Well-known app → URL mapping (expanded) ──────────────────────────────
KNOWN_URLS: dict[str, str] = {
    # Productivity
    "gmail":       "https://mail.google.com",
    "google mail": "https://mail.google.com",
    "whatsapp":    "https://web.whatsapp.com",
    "notion":      "https://www.notion.so",
    "calendar":    "https://calendar.google.com",
    "google calendar": "https://calendar.google.com",
    "drive":       "https://drive.google.com",
    "google drive":"https://drive.google.com",
    "docs":        "https://docs.google.com",
    "sheets":      "https://sheets.google.com",
    "slides":      "https://slides.google.com",
    "meet":        "https://meet.google.com",
    "trello":      "https://trello.com",
    "asana":       "https://app.asana.com",
    "jira":        "https://jira.atlassian.com",
    "linear":      "https://linear.app",
    "clickup":     "https://app.clickup.com",
    "slack":       "https://app.slack.com",
    "discord":     "https://discord.com/app",
    "teams":       "https://teams.microsoft.com",
    "zoom":        "https://zoom.us",
    "figma":       "https://figma.com",
    "github":      "https://github.com",
    "gitlab":      "https://gitlab.com",
    # Social / media
    "youtube":     "https://www.youtube.com",
    "twitter":     "https://twitter.com",
    "x":           "https://x.com",
    "instagram":   "https://www.instagram.com",
    "facebook":    "https://www.facebook.com",
    "reddit":      "https://www.reddit.com",
    "linkedin":    "https://www.linkedin.com",
    "tiktok":      "https://www.tiktok.com",
    "pinterest":   "https://www.pinterest.com",
    "telegram":    "https://web.telegram.org",
    # Search / news
    "google":      "https://www.google.com",
    "bing":        "https://www.bing.com",
    "duckduckgo":  "https://www.duckduckgo.com",
    "brave":       "https://search.brave.com",
    "news":        "https://news.google.com",
    "bbc":         "https://www.bbc.com",
    # Shopping
    "amazon":      "https://www.amazon.com",
    "flipkart":    "https://www.flipkart.com",
    "ebay":        "https://www.ebay.com",
    # Finance
    "paypal":      "https://www.paypal.com",
    "stripe":      "https://dashboard.stripe.com",
    "coinbase":    "https://www.coinbase.com",
    # Dev tools
    "stackoverflow": "https://stackoverflow.com",
    "chatgpt":     "https://chat.openai.com",
    "claude":      "https://claude.ai",
    "perplexity":  "https://www.perplexity.ai",
    "vercel":      "https://vercel.com",
    "netlify":     "https://netlify.com",
    "heroku":      "https://heroku.com",
    # Cloud
    "aws":         "https://console.aws.amazon.com",
    "azure":       "https://portal.azure.com",
    "gcp":         "https://console.cloud.google.com",
}

SEARCH_URLS: dict[str, str] = {
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "google": "https://www.google.com/search?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "amazon": "https://www.amazon.com/s?k={query}",
    "github": "https://github.com/search?q={query}",
    "stackoverflow": "https://stackoverflow.com/search?q={query}",
    "twitter": "https://twitter.com/search?q={query}",
    "x": "https://x.com/search?q={query}",
}


def resolve_url(app_name: str, intent: IntentResult) -> str:
    """
    Resolve any app name or website to a URL.

    Priority:
      1. URL already in intent.data
      2. KNOWN_URLS lookup (case-insensitive, partial match)
      3. If app_name looks like a domain, prefix https://
      4. Google search as last resort
    """
    # Already have a URL
    if intent.data.get("url"):
        return intent.data["url"]

    # Check data.target for a URL
    target = (intent.target or "").strip().lower()

    # Normalise app name
    name = (app_name or "").strip().lower()

    # Exact match
    if name in KNOWN_URLS:
        return KNOWN_URLS[name]

    # Partial match (e.g. "google docs" matches "docs")
    for key, url in KNOWN_URLS.items():
        if key in name or name in key:
            return url

    # Looks like a bare domain (youtube.com, example.io, etc.)
    domain_re = re.compile(r"^[\w\-]+\.(com|io|org|net|ai|app|co|in|uk|de|fr)$", re.I)
    if domain_re.match(name):
        return f"https://{name}"

    # Partial domain without TLD — assume .com
    if re.match(r"^[a-z0-9\-]+$", name) and len(name) > 2:
        return f"https://www.{name}.com"

    # Last resort: Google search
    query = (intent.target or intent.raw_text or name).strip().replace(" ", "+")
    return f"https://www.google.com/search?q={query}"


def resolve_search_url(app_name: str, query: str) -> str:
    name = (app_name or "google").strip().lower()
    encoded = quote_plus(query.strip())
    if not encoded:
        return resolve_url(name, IntentResult("open_app", name, name, {}, 1.0, ""))
    if name in SEARCH_URLS:
        return SEARCH_URLS[name].format(query=encoded)
    for key, template in SEARCH_URLS.items():
        if key in name or name in key:
            return template.format(query=encoded)
    base = resolve_url(name, IntentResult("open_app", name, name, {}, 1.0, ""))
    if "google.com/search" in base:
        return base
    return f"https://www.google.com/search?q={quote_plus(name + ' ' + query)}"


class ActionRouter:
    def check_health(self) -> tuple[bool, str]:
        """Verify that the browser backend is reachable."""
        try:
            return BaseExecutor.check_health()
        except Exception as e:
            return False, str(e)

    def route(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """
        Dispatch intent to executor.
        Any app → resolved URL → browser. No hardcoded dead-ends.
        Returns (success, human-readable result message).
        """
        logger.info(f"Routing: intent={intent.intent}, app={intent.app}")

        if intent.intent == "unknown" or intent.confidence < 0.5:
            return False, f"Couldn't understand command. (confidence={intent.confidence:.0%})"

        if intent.intent in ("pc_action", "chat_reflex"):
            safety = intent.data.get("safety_level", "safe")
            if safety == "forbidden":
                return False, f"Refused unsafe PC action: {intent.data.get('operation', intent.target)}"
            return pc_executor.execute(intent, context)

        if intent.intent == "chat":
            return chat_executor.execute(intent, context)

        if intent.intent == "taught_workflow":
            return browser_executor.run_taught_workflow(intent.data.get("steps", []))

        missing = self._check_params(intent)
        if missing:
            return False, f"Missing required info: {', '.join(missing)}"

        # ── 1. Dedicated executor (known apps, specific intents) ─────────
        route_key = (intent.intent, intent.app)
        if route_key in ROUTE_TABLE:
            executor, method = ROUTE_TABLE[route_key]
            try:
                return getattr(executor, method)(intent, context)
            except Exception as e:
                logger.exception(f"Dedicated executor failed: {e}")
                return False, f"Action failed: {str(e)[:100]}"

        # ── 2. open_app — any app, any website ──────────────────────────
        if intent.intent == "open_app":
            url = resolve_url(intent.app or intent.target or "", intent)
            intent.data["url"] = url
            logger.info(f"Opening: {url}")
            try:
                return browser_executor.open_url(intent, context)
            except Exception as e:
                return False, f"Failed to open {url}: {str(e)[:80]}"

        # ── 3. summarize — any open page ─────────────────────────────────
        if intent.intent == "summarize":
            try:
                return browser_executor.summarize_page(intent, context)
            except Exception as e:
                return False, f"Summarize failed: {str(e)[:80]}"

        # ── 4. browser_action / send_message on unknown app ─────────────
        # Convert to adaptive browser task on whatever page is open
        if intent.intent in ("browser_action", "send_message", "create_task"):
            if intent.data.get("action") == "search":
                query = intent.data.get("query") or intent.data.get("text") or intent.target or intent.raw_text
                url = resolve_search_url(intent.app, query)
                search_intent = IntentResult(
                    intent="open_app",
                    app=intent.app,
                    target=query,
                    data={"url": url},
                    confidence=1.0,
                    raw_text=intent.raw_text,
                )
                return browser_executor.open_url(search_intent, context)

            # If targeting a specific app, open it first if not already there
            app_name = intent.app or ""
            if app_name.lower() not in ("browser", "unknown", "current", ""):
                current_url = (context.dom or {}).get("url", "") or context.url or BaseExecutor.get_active_page_url_safe()
                target_url = resolve_url(app_name, intent)
                if app_name.lower() not in current_url.lower():
                    logger.info(f"Navigating to {target_url} before action")
                    nav_intent = IntentResult(
                        intent="open_app", app=app_name, target=app_name,
                        data={"url": target_url}, confidence=1.0, raw_text=""
                    )
                    ok, msg = browser_executor.open_url(nav_intent, context, wait=True)
                    if not ok:
                        return False, f"Could not navigate to {target_url}: {msg}"

            # Now run adaptive browser task with the original goal
            if not intent.data.get("goal"):
                intent.data["goal"] = intent.raw_text or f"{intent.intent} on {intent.app}"
            intent.data.setdefault("action", "auto")
            intent.data.setdefault("max_steps", 8)
            try:
                return browser_executor.execute(intent, context)
            except Exception as e:
                logger.exception(f"Adaptive browser task failed: {e}")
                return False, f"Browser task failed: {str(e)[:100]}"

        return False, f"No handler for: {intent.intent} on {intent.app}"

    def _check_params(self, intent: IntentResult) -> list[str]:
        missing = []
        if intent.intent == "send_message" and intent.app in ("whatsapp", "gmail"):
            if not intent.target:
                missing.append("recipient")
        return missing
