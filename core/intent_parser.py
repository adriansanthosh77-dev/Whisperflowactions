"""
intent_parser.py — Convert transcribed text + context into structured IntentResult.
Removed OpenAI SDK for Python 3.14 compatibility.
"""

import json
import time
import logging
import os
import requests
from models.intent_schema import IntentResult, Context
logger = logging.getLogger(__name__)

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

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
    if context.active_app: ctx_parts.append(f"active_app: {context.active_app}")
    if context.url: ctx_parts.append(f"url: {context.url}")
    if context.selected_text: ctx_parts.append(f"selected_text: {context.selected_text[:300]}")
    if context.dom:
        dom_summary = {
            "title": context.dom.get("title", ""),
            "url": context.dom.get("url", ""),
            "elements": context.dom.get("elements", [])[:15],
        }
        ctx_parts.append(f"dom: {json.dumps(dom_summary)[:2500]}")
    
    ctx_str = "\n".join(ctx_parts) if ctx_parts else "none"
    return f"Command: {text}\nContext:\n{ctx_str}"

class IntentParser:
    def __init__(self, model: str = None):
        self.provider = LLM_PROVIDER
        self.model = model or (OPENAI_MODEL if self.provider == "openai" else OLLAMA_MODEL)
        self.api_key = os.getenv("OPENAI_API_KEY")

    def parse(self, text: str, context: Context) -> IntentResult:
        start = time.time()
        try:
            if self.provider == "ollama":
                parsed = self._parse_ollama(text, context)
            else:
                parsed = self._parse_openai(text, context)

            elapsed = time.time() - start
            logger.info(f"Intent parsed in {elapsed:.2f}s via {self.provider}")

            return IntentResult(
                intent=parsed.get("intent", "unknown"),
                app=parsed.get("app", "unknown"),
                target=parsed.get("target", ""),
                data=parsed.get("data", {}),
                confidence=float(parsed.get("confidence", 1.0)),
                raw_text=text,
            )
        except Exception as e:
            logger.error(f"Intent parser error: {e}")
            return self._fallback(text)

    def _parse_openai(self, text: str, context: Context) -> dict:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(text, context)},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        resp.raise_for_status()
        return json.loads(resp.json()["choices"][0]["message"]["content"])

    def _parse_ollama(self, text: str, context: Context) -> dict:
        url = f"{OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(text, context)},
            ],
            "stream": False,
            "format": "json"
        }
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        return json.loads(resp.json()["message"]["content"])

    def _fallback(self, text: str) -> IntentResult:
        return IntentResult(intent="unknown", app="unknown", target="", data={}, confidence=0.0, raw_text=text)
