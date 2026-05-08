"""
planner.py — Multi-step command planner with streaming execution.

Converts natural speech into a ordered list of IntentResult steps,
yielding each step as soon as it's parsed so the executor can start
immediately — giving the perception of near-instant response.

Supports OpenAI (streaming) and Ollama (non-streaming fallback).

Example:
  "Open Gmail, find the last email from John, and draft a professional reply"
  → step 1: open_app      (gmail)
  → step 2: summarize     (gmail, target=john)
  → step 3: reply_professionally (gmail)
"""

import json
import os
import re
import time
import logging
import requests
from typing import Generator, Optional
from openai import OpenAI
from dotenv import load_dotenv
from models.intent_schema import IntentResult, Context

load_dotenv()
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "openai").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3").strip()
OPENAI_MODEL    = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

_openai_client: Optional[OpenAI] = None

def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client

def _has_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "sk-..." and not key.endswith("..."))


# ── System prompt ─────────────────────────────────────────────────────────
PLANNER_PROMPT = """You are an action planner for a voice assistant controlling Chrome.
Break the user's command into an ordered list of atomic steps.

INTENTS: send_message | summarize | reply_professionally | create_task | open_app | browser_action | unknown
APP: any app or website name in lowercase — e.g. whatsapp, gmail, notion, youtube, reddit, twitter,
     linear, github, stripe, chatgpt, or any domain the user mentions. Use "browser" for the current page.

Return a JSON array (no prose, no markdown):
[
  {"intent":"...","app":"...","target":"...","data":{...},"confidence":0.9},
  ...
]

DATA by intent:
- send_message:          {"message":"text"}
- summarize:             {"style":"bullet|paragraph"}
- reply_professionally:  {"tone":"formal|friendly","key_points":["..."]}
- create_task:           {"title":"...","description":"...","due":""}
- open_app:              {}  (router resolves URL from app name automatically)
- browser_action:        {"goal":"what to accomplish","action":"click|type|press|auto","selector":"","text":"","key":"","labels":["..."],"expected_text":"","max_steps":8}

EXAMPLES:
- "open youtube and search for lo-fi music"
  [{"intent":"open_app","app":"youtube","target":"","data":{},"confidence":0.95},
   {"intent":"browser_action","app":"youtube","target":"","data":{"goal":"search for lo-fi music","action":"auto","max_steps":4},"confidence":0.95}]

- "go to reddit and find the top post in r/programming"
  [{"intent":"open_app","app":"reddit","target":"","data":{},"confidence":0.95},
   {"intent":"browser_action","app":"reddit","target":"","data":{"goal":"navigate to r/programming and find top post","action":"auto","max_steps":5},"confidence":0.9}]

- "draft a gmail to sarah about the meeting tomorrow"
  [{"intent":"send_message","app":"gmail","target":"sarah","data":{"message":"Hi Sarah, just a reminder about our meeting tomorrow."},"confidence":0.95}]

RULES:
- Always open the app first if context.url does not already show it.
- Single-step commands → 1-element array.
- Confidence < 0.6 → set intent to "unknown".
- Never hallucinate content not in the command.
- The user may speak in any language — extract intent regardless.
- RELEVANCE: Respect the "Adaptive Memory" hints (past runs) AND "Session History" (recent commands) to handle follow-up requests or build on previous successes.
"""


# ── Step parser ───────────────────────────────────────────────────────────

def _build_user_message(text: str, context: Context) -> str:
    parts = []
    if context.url:
        parts.append(f"url: {context.url}")
    if context.active_app:
        parts.append(f"active_app: {context.active_app}")
    if context.selected_text:
        parts.append(f"selected_text: {context.selected_text[:200]}")
    if context.dom:
        dom = {
            "title": context.dom.get("title", ""),
            "url":   context.dom.get("url", ""),
            "headings": context.dom.get("appStructure", {}).get("headings", [])[:4],
            "elements": context.dom.get("elements", [])[:10],
        }
        parts.append(f"dom: {json.dumps(dom)[:1500]}")
    
    if context.learning_hints:
        hints = "\n- ".join(context.learning_hints)
        parts.append(f"Adaptive Memory (Hints from past runs):\n- {hints}")
    
    if context.history:
        h_str = "\n".join([f"- {h.get('command')} ({'Success' if h.get('success') else 'Failed'})" for h in context.history])
        parts.append(f"Recent Session History (Short-term memory):\n{h_str}")
        
    ctx_str = "\n".join(parts) or "none"
    return f"Command: {text}\nContext:\n{ctx_str}"


def _parse_step(raw: dict) -> IntentResult:
    return IntentResult(
        intent=raw.get("intent", "unknown"),
        app=raw.get("app", "unknown"),
        target=raw.get("target", ""),
        data=raw.get("data", {}),
        confidence=float(raw.get("confidence", 1.0)),
        raw_text="",
    )


def _extract_json_objects(text: str) -> list[dict]:
    """
    Extract all {...} JSON objects from a potentially partial string.
    Used to parse the streamed array incrementally.
    """
    results = []
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                try:
                    obj = json.loads(text[start:i+1])
                    results.append(obj)
                except json.JSONDecodeError:
                    pass
                start = -1
    return results


# ── Streaming planner (OpenAI) ────────────────────────────────────────────

def _stream_plan_openai(text: str, context: Context, prompt: str = PLANNER_PROMPT, model: str = OPENAI_MODEL) -> Generator[IntentResult, None, None]:
    """
    Stream the plan array from OpenAI with Multimodal (Vision) support.
    """
    user_msg_text = _build_user_message(text, context)
    
    # ── MULTIMODAL PLANNING ──────────────────────────────────────────────
    # If we have a recent screenshot, send it to help the planner understand layout.
    content = [{"type": "text", "text": user_msg_text}]
    
    shot_path = context.dom.get("screenshot") if context.dom else None
    if shot_path and os.path.exists(shot_path):
        import base64
        with open(shot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        content.append({
            "type": "image_url", 
            "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "low"}
        })

    stream = _get_openai_client().chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user",   "content": content},
        ],
        max_tokens=500,
        temperature=0.0,
        stream=True,
    )

    buffer = ""
    yielded = 0

    for chunk in stream:
        delta = chunk.choices[0].delta.content or ""
        buffer += delta

        objects = _extract_json_objects(buffer)
        while len(objects) > yielded:
            step_dict = objects[yielded]
            yielded += 1
            step = _parse_step(step_dict)
            logger.info(f"Plan step {yielded}: {step.intent} → {step.app} [{step.target}]")
            yield step


# ── Ollama planner (non-streaming fallback) ───────────────────────────────

def _plan_ollama(text: str, context: Context) -> Generator[IntentResult, None, None]:
    """
    Call Ollama and parse the full array response.
    Ollama streaming for JSON arrays is unreliable, so we wait for
    the full response then yield steps quickly.
    """
    user_msg = _build_user_message(text, context)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "stream": False,
        "options": {"temperature": 0.0, "num_predict": 400},
    }
    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=15)
    resp.raise_for_status()

    content = resp.json().get("message", {}).get("content", "")

    # Strip markdown code fences if present
    content = re.sub(r"```(?:json)?", "", content).strip().strip("```")

    steps_raw = json.loads(content)
    for i, raw in enumerate(steps_raw, 1):
        step = _parse_step(raw)
        logger.info(f"Plan step {i}: {step.intent} → {step.app} [{step.target}]")
        yield step


# ── Public API ────────────────────────────────────────────────────────────

class Planner:
    def __init__(self, model: str = None):
        self.model = model or OPENAI_MODEL
        self.custom_system_prompt = None
        logger.info(f"Planner using {self.model}")

    def set_persona(self, system_prompt: str):
        self.custom_system_prompt = system_prompt

    def plan(self, text: str, context: Context) -> Generator[IntentResult, None, None]:
        start = time.time()
        try:
            if LLM_PROVIDER == "ollama":
                yield from _plan_ollama(text, context)
            elif _has_openai_key():
                prompt = self.custom_system_prompt or PLANNER_PROMPT
                yield from _stream_plan_openai(text, context, prompt, self.model)
            else:
                logger.warning("No LLM available for planning — single fallback step")
                yield from self._fallback(text)
        except requests.ConnectionError:
            logger.error(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}")
            yield from self._fallback(text)
        except Exception as e:
            logger.error(f"Planner error: {e}")
            yield from self._fallback(text)

        logger.info(f"Total plan generation: {time.time() - start:.2f}s")

    def _fallback(self, text: str) -> Generator[IntentResult, None, None]:
        """Single rule-based step for when LLM is unavailable."""
        t = text.lower()
        if any(k in t for k in ["send", "message", "tell", "text"]):
            words = text.split()
            kws = {"send", "message", "tell", "text"}
            name = next((w for w in words if w.lower() not in kws and w[0].isupper()), "")
            app = "whatsapp" if "whatsapp" in t else "gmail"
            yield IntentResult("send_message", app, name, {"message": text}, 0.5, text)
        elif "summarize" in t or "summary" in t:
            yield IntentResult("summarize", "browser", "current_page", {"style": "bullet"}, 0.8, text)
        elif "open" in t:
            for app in ["whatsapp", "gmail", "notion"]:
                if app in t:
                    yield IntentResult("open_app", app, app, {}, 0.9, text)
                    return
            yield IntentResult("unknown", "unknown", "", {}, 0.0, text)
        else:
            yield IntentResult("unknown", "unknown", "", {}, 0.0, text)
