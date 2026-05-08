"""
intent_parser.py — Convert transcribed text + context into structured IntentResult.

Uses GPT-4o-mini with a strict JSON schema prompt.
Target latency: <1.5s.
"""

import json
import time
import logging
import os
from openai import OpenAI
from dotenv import load_dotenv
from models.intent_schema import IntentResult, Context

load_dotenv()
logger = logging.getLogger(__name__)

client = None


def get_openai_client() -> OpenAI:
    global client
    if client is None:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return client


def has_valid_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "sk-..." and not key.endswith("..."))

SYSTEM_PROMPT = """Intent classifier for a voice assistant controlling Chrome. Return strict JSON only.

INTENTS: send_message | summarize | reply_professionally | create_task | open_app | browser_action | unknown
APPS: whatsapp | gmail | notion | browser | unknown

JSON FORMAT:
{"intent":"...","app":"...","target":"...","data":{...},"confidence":0.0}

DATA by intent:
- send_message: {"message":"text"}
- summarize: {"style":"bullet|paragraph"}
- reply_professionally: {"tone":"formal|friendly","key_points":["..."]}
- create_task: {"title":"...","description":"...","due":""}
- open_app: {}
- browser_action: {"goal":"...","action":"click|type|press|auto","selector":"","text":"","key":"","labels":["..."],"expected_text":"","max_steps":6}

RULES: Infer app from URL/context if ambiguous. Use DOM selectors when available. Confidence<0.6 → unknown. Never hallucinate content.
"""


def build_user_message(text: str, context: Context) -> str:
    ctx_parts = []
    if context.active_app:
        ctx_parts.append(f"active_app: {context.active_app}")
    if context.url:
        ctx_parts.append(f"url: {context.url}")
    if context.selected_text:
        ctx_parts.append(f"selected_text: {context.selected_text[:300]}")
    if context.clipboard:
        ctx_parts.append(f"clipboard: {context.clipboard[:150]}")
    if context.dom:
        # Send only the bare minimum DOM needed for grounding
        dom_summary = {
            "title": context.dom.get("title", ""),
            "url": context.dom.get("url", ""),
            "activeElement": context.dom.get("activeElement", ""),
            # Only headings + forms — skip landmarks/topSections for speed
            "headings": context.dom.get("appStructure", {}).get("headings", [])[:6],
            "forms": context.dom.get("appStructure", {}).get("forms", [])[:3],
            "elements": context.dom.get("elements", [])[:15],  # was 25
        }
        ctx_parts.append(f"dom: {json.dumps(dom_summary)[:2500]}")
    if context.learning_hints:
        ctx_parts.append("hints:\n" + "\n".join(f"- {h}" for h in context.learning_hints[:5]))

    ctx_str = "\n".join(ctx_parts) if ctx_parts else "none"
    return f"Command: {text}\nContext:\n{ctx_str}"


class IntentParser:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model

    def parse(self, text: str, context: Context) -> IntentResult:
        start = time.time()

        try:
            if not has_valid_openai_key():
                return self._fallback(text)
            response = get_openai_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_message(text, context)},
                ],
                max_tokens=200,   # intent JSON is always short
                temperature=0.0,  # fully deterministic
                response_format={"type": "json_object"},
            )

            elapsed = time.time() - start
            logger.info(f"Intent parsed in {elapsed:.2f}s")

            raw_json = response.choices[0].message.content
            parsed = json.loads(raw_json)

            intent = IntentResult(
                intent=parsed.get("intent", "unknown"),
                app=parsed.get("app", "unknown"),
                target=parsed.get("target", ""),
                data=parsed.get("data", {}),
                confidence=float(parsed.get("confidence", 1.0)),
                raw_text=text,
            )

            logger.info(f"Intent: {intent.intent} | App: {intent.app} | Target: '{intent.target}'")
            return intent

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return self._fallback(text)
        except Exception as e:
            logger.error(f"Intent parser error: {e}")
            return self._fallback(text)

    def _fallback(self, text: str) -> IntentResult:
        """Rule-based fallback for when API is unavailable."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["send", "message", "tell", "text"]):
            # Try to extract name: "tell John..." → target=John
            words = text.split()
            intent_words = {"send", "message", "tell", "text"}
            name = next((w for w in words if w.lower() not in intent_words and w[0].isupper()), "")
            app = "whatsapp" if "whatsapp" in text_lower else "gmail"
            msg = text  # full text as fallback message
            return IntentResult(intent="send_message", app=app, target=name,
                                data={"message": msg}, confidence=0.5, raw_text=text)

        if "summarize" in text_lower or "summary" in text_lower:
            return IntentResult(intent="summarize", app="browser", target="current_page",
                                data={"style": "bullet"}, confidence=0.8, raw_text=text)

        if "open" in text_lower:
            for app in ["whatsapp", "gmail", "notion"]:
                if app in text_lower:
                    return IntentResult(intent="open_app", app=app, target=app,
                                        data={}, confidence=0.9, raw_text=text)

        if any(kw in text_lower for kw in ["click", "press", "type"]):
            action = "click" if "click" in text_lower else "press" if "press" in text_lower else "type"
            return IntentResult(intent="browser_action", app="browser", target="current_page",
                                data={"goal": text, "action": action, "text": text, "selector": "", "key": ""},
                                confidence=0.55, raw_text=text)

        return IntentResult(intent="unknown", app="unknown", target="",
                            data={}, confidence=0.0, raw_text=text)
