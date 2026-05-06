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

SYSTEM_PROMPT = """You are an intent classification engine for a voice assistant that controls Chrome browser apps.

Extract structured intent from the user's voice command. Always return valid JSON only — no prose, no markdown.

SUPPORTED INTENTS:
- send_message: send a message via WhatsApp or Gmail
- summarize: summarize current page, email thread, or selected text
- reply_professionally: compose a professional reply to an email
- create_task: create a task/note in Notion
- open_app: open or switch to a browser app (whatsapp, gmail, notion)
- browser_action: click, type, press a key, or complete a bounded multi-step browser task using DOM/mouse state
- unknown: when the command doesn't map to any supported intent

SUPPORTED APPS: whatsapp, gmail, notion, browser, unknown

OUTPUT FORMAT (strict JSON):
{
  "intent": "<one of the intents above>",
  "app": "<one of the apps above>",
  "target": "<contact name | page | task title | app name | empty string>",
  "data": {<intent-specific payload>},
  "confidence": <0.0 to 1.0>
}

DATA PAYLOADS BY INTENT:
- send_message: {"message": "text to send"}
- summarize: {"style": "bullet|paragraph"} 
- reply_professionally: {"tone": "formal|friendly", "key_points": ["..."]}
- create_task: {"title": "...", "description": "...", "due": "...or empty"}
- open_app: {}
- browser_action: {"goal": "what should be accomplished", "action": "click|type|press|auto", "selector": "...or empty", "text": "...or empty", "key": "...or empty", "labels": ["..."], "expected_text": "...or empty", "max_steps": 6}

RULES:
- If app is ambiguous and selected_text or URL is provided, infer from context.
- Prefer DOM selectors from context.dom.elements over visual/screenshot descriptions.
- For click actions, use selector when a matching DOM element is available; use x/y only when the user explicitly refers to mouse position.
- For type actions, put the typed content in data.text and the destination selector in data.selector when known.
- For multi-step browser tasks, set action to "auto", describe the goal, and include expected_text when completion can be verified from page text.
- For WhatsApp messages: extract recipient name from "tell X" / "message X" / "send X".
- Confidence below 0.6 → set intent to "unknown".
- Never hallucinate recipients or content not in the command.
"""


def build_user_message(text: str, context: Context) -> str:
    ctx_parts = []
    if context.active_app:
        ctx_parts.append(f"active_app: {context.active_app}")
    if context.url:
        ctx_parts.append(f"url: {context.url}")
    if context.selected_text:
        ctx_parts.append(f"selected_text: {context.selected_text[:500]}")
    if context.clipboard:
        ctx_parts.append(f"clipboard: {context.clipboard[:200]}")
    if context.mouse:
        ctx_parts.append(f"mouse: {json.dumps(context.mouse)[:200]}")
    if context.dom:
        dom_summary = {
            "title": context.dom.get("title", ""),
            "url": context.dom.get("url", ""),
            "activeElement": context.dom.get("activeElement", ""),
            "appStructure": context.dom.get("appStructure", {}),
            "elements": context.dom.get("elements", [])[:25],
        }
        ctx_parts.append(f"dom: {json.dumps(dom_summary)[:5000]}")
    if context.learning_hints:
        ctx_parts.append("learning_hints:\n" + "\n".join(f"- {h}" for h in context.learning_hints[:8]))

    ctx_str = "\n".join(ctx_parts) if ctx_parts else "none"
    return f"Voice command: {text}\n\nContext:\n{ctx_str}"


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
                max_tokens=300,
                temperature=0.1,  # low temp for deterministic JSON
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
