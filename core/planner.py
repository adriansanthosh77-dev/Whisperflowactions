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
import rapidfuzz
import requests
from typing import Generator, Optional
from core.semantic_matcher import semantic_match
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────
LLM_PROVIDER    = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL", "llama3.2:1b").strip()
FAST_PLANNER    = os.getenv("FAST_PLANNER", "true").strip().lower() not in ("0", "false", "no")
_OLLAMA_MODEL_CACHE: Optional[str] = None
DESKTOP_APPS = {
    "notepad", "calculator", "calc", "paint", "cmd", "powershell",
    "terminal", "windows terminal", "chrome", "edge", "brave", "brave browser",
    "vscode", "vs code", "visual studio code", "explorer",
}

# Pre-compiled regex patterns for _fast_plan hot path
_R = {
    "dictate_in":        re.compile(r'^dictate\s+in\s+([a-zA-Z0-9\s]{2,20})$', re.I),
    "save_as":           re.compile(r'^(?:save as|save this as|name this|call this)\s+(.+)$', re.I),
    "switch_fast":       re.compile(r"^(?:switch to|switch app to|focus on|switch)\s+(.+)$", re.I),
    "type_fast":         re.compile(r"^(?:type|dictate|just type|enter)\s+(.+)$", re.I),
    "remind":            re.compile(r"^(?:remind me|set a reminder|set reminder)\s+in\s+(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s+(?:to|that|about)\s+(.+)$", re.I),
    "open_search":       re.compile(r"^(?:open|go to|launch|execute|run)\s+(.+?)\s+(?:and\s+)?(?:search(?: for)?|find|look up)\s+(.+)$", re.I),
    "find_page":         re.compile(r"^(?:find on page|find in page|search this page for|find text)\s+(.+)$", re.I),
    "find_my":           re.compile(r"^(?:find|locate)\s+(?:my\s+|the\s+)(.+)$", re.I),
    "plain_search":      re.compile(r"^(?:search(?: for)?|find(?!\s+(?:file|folder|document))|look up)\s+(.+?)(?:\s+(?:on|in|at)\s+(.+))?$", re.I),
    "ordinal_click":     re.compile(r"^(?:click|open|select|hit)\s+(?:the\s+)?(first|second|third|fourth|fifth|last)\s+(.+)$", re.I),
    "send_message":      re.compile(r"^(draft|send|write)\s+(?:a\s+)?(?:message|email|mail|whatsapp)?\s*(?:to|for)\s+(.+?)\s+(?:saying|that says|with message|message)\s+(.+)$", re.I),
    "chat_wake":         re.compile(r"^(?:hey|hello|hi|wake up|morning|afternoon|evening)\s+jarvis.*$", re.I),
    "chat_greeting":     re.compile(r"^(?:hello|hi|hey|greetings|morning|afternoon|evening)(?:\s+jarvis)?.*$", re.I),
    "chat_identity":     re.compile(r"^.*(?:who\s+are\s+you|what\s+is\s+your\s+name|describe\s+yourself).*$", re.I),
    "chat_status":       re.compile(r"^.*(?:how\s+are\s+you|how's\s+it\s+going).*$", re.I),
    "chat_voice_desc":   re.compile(r"^.*(?:describe\s+my\s+voice|what\s+do\s+i\s+sound\s+like).*$", re.I),
    "chat_gratitude":    re.compile(r"^.*(?:thank\s+you|thanks|cheers|nice one).*$", re.I),
    "chat_reflex":       re.compile(r"^(write\s+this\s+back|draft\s+a\s+message|grammar\s+correct|correct\s+this|reply)\s*[:\s]\s*(.+)$", re.I),
    "switch_url":        re.compile(r"^(?:switch to|switch app to|go to|focus on)\s+(.+)$", re.I),
    "launch":            re.compile(r"^(?:launch|start|open app|open)\s+(.+)$", re.I),
    "file_type_suffix":  re.compile(r"^(?:open|launch|show|find|search(?: for)?|go to)\s+(.+?)\s+(?:file|folder|document|dir|directory)$", re.I),
    "file_type_prefix":  re.compile(r"^(?:open|launch|show|find|search(?: for)?|go to)\s+(?:file|folder|document|dir|directory)\s+(.+)$", re.I),
    "screenshot":        re.compile(r"^(?:take screenshot|screenshot|capture screen)$", re.I),
    "download":          re.compile(r"^(?:download|save|get)\s+(?:the\s+|my\s+|his\s+|her\s+|this\s+)?(?:photo|image|file|video|it|picture)$", re.I),
    "paste_folder":      re.compile(r"^(?:paste|copy\s+in|copy\s+and\s+paste\s+in|save\s+in|move\s+to)\s+(?:the\s+)?(?:it\s+in\s+|this\s+in\s+)?(.+?)\s+(?:folder|dir|directory)$", re.I),
    "paste":             re.compile(r"^(?:paste)(?:\s+(.+))?$", re.I),
    "copy":              re.compile(r"^(?:copy)(?:\s+(.+))?$", re.I),
    "rename_dual":       re.compile(r"^(?:rename|name)\s+(.+?)\s+(?:to|as|into)\s+(.+)$", re.I),
    "rename_single":     re.compile(r"^(?:rename|name)\s+(?:this|it|the selected item)?\s*(?:to|as|into)\s+(.+)$", re.I),
    "describe_screen":   re.compile(r"^(?:what is on|describe|look at|see|show me)\s+(?:the\s+|my\s+)?(?:screen|monitor|desktop|it)$", re.I),
    "switch_generic":    re.compile(r"^(?:switch|next|change)\s+(?:window|app|tab)$", re.I),
    "guarded":           re.compile(r"^(delete|kill|run command|install)\s+(.+)$", re.I),
    "open_that":         re.compile(r"^(?:open|show)\s+(?:it|that|the\s+screenshot)$", re.I),
    "open_only":         re.compile(r"^(?:open|go to|launch|execute|run)\s+(.+)$", re.I),
    "type_only":         re.compile(r"^(?:type|enter)\s+(.+)$", re.I),
    "click":             re.compile(r"^(?:click|press|tap)\s+(.+)$", re.I),
}


def _resolve_ollama_model() -> str:
    global _OLLAMA_MODEL_CACHE
    if _OLLAMA_MODEL_CACHE:
        return _OLLAMA_MODEL_CACHE

    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        configured = OLLAMA_MODEL
        if configured in models or f"{configured}:latest" in models:
            _OLLAMA_MODEL_CACHE = configured
        elif models:
            _OLLAMA_MODEL_CACHE = models[0]
            logger.warning(
                "Configured Ollama model '%s' is not installed; using '%s'.",
                configured,
                _OLLAMA_MODEL_CACHE,
            )
        else:
            _OLLAMA_MODEL_CACHE = configured
    except Exception:
        _OLLAMA_MODEL_CACHE = OLLAMA_MODEL
    return _OLLAMA_MODEL_CACHE


# ── Learned Reflexes (Teach Mode) ─────────────────────────────────────────
LEARNED_REFLEXES_PATH = os.path.join("data", "learned_reflexes.json")
_CURRENT_CONTEXT = None  # Set by plan() before calling _fast_plan

def _load_learned_reflexes() -> dict:
    """Load user-taught reflexes from disk."""
    if os.path.exists(LEARNED_REFLEXES_PATH):
        try:
            with open(LEARNED_REFLEXES_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}

def _save_learned_reflex(trigger: str, operation: str, extra: dict = None):
    """Save a new user-taught reflex to disk permanently."""
    reflexes = _load_learned_reflexes()
    reflexes[trigger.lower().strip()] = {
        "operation": operation,
        **(extra or {})
    }
    os.makedirs(os.path.dirname(LEARNED_REFLEXES_PATH), exist_ok=True)
    with open(LEARNED_REFLEXES_PATH, 'w') as f:
        json.dump(reflexes, f, indent=2)
    logger.info(f"Learned new reflex: '{trigger}' -> {operation}")

def teach_reflex(trigger: str, operation: str, extra: dict = None):
    """Public API for teaching JARVIS a new reflex."""
    _save_learned_reflex(trigger, operation, extra)
    return f"Got it! I'll remember '{trigger}' from now on."


# ── Fuzzy Matching Engine ─────────────────────────────────────────────────
def _fuzzy_match(query: str, keys: list, cutoff: float = 87.0) -> Optional[str]:
    """Find the closest matching reflex key using rapidfuzz."""
    if not keys:
        return None
    
    # 1. Direct Fuzzy Match (Layer 2)
    result = rapidfuzz.process.extractOne(query, keys, score_cutoff=cutoff)
    if result:
        match, score, index = result
        logger.info(f"Fuzzy matched '{query}' -> '{match}' (score: {score:.1f})")
        return match
    
    # 2. Semantic Token Match (Layer 3)
    # Higher cutoff because semantic matching is more aggressive
    match = semantic_match(query, keys, threshold=cutoff + 5.0)
    if match:
        return match

    return None


# ── Context Awareness ─────────────────────────────────────────────────────
def _apply_context(result: IntentResult, context) -> IntentResult:
    """Adjust reflex behavior based on what the user is currently doing.

    Example: 'play' on YouTube -> browser click instead of media key.
    """
    if context is None:
        return result

    active_url = ""
    if hasattr(context, 'dom') and context.dom and isinstance(context.dom, dict):
        active_url = context.dom.get("url", "").lower()

    op = result.data.get("operation", "")

    # On a streaming site? Route media commands to the browser
    streaming_sites = ["youtube.com", "spotify.com", "netflix.com", "twitch.tv", "primevideo.com"]
    if active_url and any(site in active_url for site in streaming_sites):
        if op in ("media_play_pause", "media_next", "media_previous"):
            action_word = op.replace("media_", "").replace("_", " ")
            return IntentResult(
                "browser_action", "browser", "",
                {"action": "click", "target": action_word, "goal": f"Click the {action_word} button"},
                result.confidence, result.raw_text,
            )

    # On a search page? Route scroll to browser scroll
    search_sites = ["google.com/search", "bing.com/search", "duckduckgo.com"]
    if active_url and any(site in active_url for site in search_sites):
        if op in ("scroll_down", "scroll_up"):
            direction = "down" if "down" in op else "up"
            return IntentResult(
                "browser_action", "browser", "",
                {"action": "scroll", "direction": direction, "goal": f"Scroll {direction}"},
                result.confidence, result.raw_text,
            )

    return result


# ── System prompt ─────────────────────────────────────────────────────────
PLANNER_PROMPT = """You are a JSON action planner for JARVIS. Output a JSON array.

INTENTS: send_message | summarize | create_task | open_app | browser_action | pc_action | chat | describe_screen | unknown

RULES:
1. Break commands into a JSON array inside a ```json block.
2. Search? Use {"intent":"browser_action","app":"browser","data":{"action":"search","query":"..."}}
3. Download? Use {"intent":"browser_action","app":"browser","data":{"action":"auto","goal":"..."}}

EXAMPLE:
```json
[
  {"intent":"open_app","app":"google","data":{}},
  {"intent":"browser_action","app":"browser","data":{"action":"search","query":"Vijay"}}
]
```
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
        parts.append(f"dom: {json.dumps(dom)[:800]}")
    
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


def _clean_app_name(value: str) -> str:
    return re.sub(r"^(the|app|website)\s+", "", value.strip().lower()).strip(" .")


def _fast_plan(text: str) -> list[IntentResult]:
    """
    Local rules for obvious commands. This keeps common voice commands fast
    and reserves Ollama/OpenAI for ambiguous multi-step reasoning.
    """
    if not FAST_PLANNER:
        return []

    raw = text.strip()
    t = raw.lower().strip().strip(".?!")
    if not t:
        return []

        return results

    # --- 0. DICTATION MODE VOICE TRIGGERS ---
    if t in ("start dictation", "begin dictation", "dictation mode"):
        return [IntentResult("dictation_mode", "pc", "", {"operation": "start", "safety_level": "safe"}, 0.99, raw)]

    if t in ("stop dictation", "end dictation", "exit dictation"):
        return [IntentResult("dictation_mode", "pc", "", {"operation": "stop", "safety_level": "safe"}, 0.99, raw)]

    dictate_in = _R["dictate_in"].match(raw)
    if dictate_in:
        app = dictate_in.group(1).strip().lower()
        return [
            IntentResult("pc_action", "pc", app, {"operation": "launch_app", "app": app, "safety_level": "safe"}, 0.99, raw),
            IntentResult("dictation_mode", "pc", "", {"operation": "start", "safety_level": "safe"}, 0.99, raw),
        ]

    # --- 1. TEACH MODE VOICE TRIGGERS ---
    from core.teach_mode import get_teach_mode
    tm = get_teach_mode()

    if t in ("record this", "start recording", "teach mode", "watch me"):
        msg = tm.start_recording()
        return [IntentResult("chat_reflex", "pc", "", {"mode": "teach", "text": msg, "safety_level": "safe"}, 0.99, raw)]

    if t in ("stop recording", "done recording", "that's it", "save recording"):
        result = tm.stop_recording()
        msg = f"Captured {result['count']} steps. Say 'save as [name]' to name this workflow."
        return [IntentResult("chat_reflex", "pc", "", {"mode": "teach_save_prompt", "text": msg, "steps": result['steps'], "safety_level": "safe"}, 0.99, raw)]

    save_match = _R["save_as"].match(raw)
    if save_match:
        trigger_name = save_match.group(1).strip()
        msg = tm.save_manual_workflow(trigger_name, tm.recorded_steps if tm.recorded_steps else [])
        return [IntentResult("chat_reflex", "pc", "", {"mode": "teach_saved", "text": msg, "safety_level": "safe"}, 0.99, raw)]

    # Check learned workflows
    workflow = tm.find_workflow(t)
    if workflow:
        results = []
        for step in workflow["steps"]:
            results.append(IntentResult(
                intent=step.get("intent", "pc_action"),
                app=step.get("app", "pc"),
                target=step.get("target", ""),
                data=step.get("data", {}),
                confidence=0.97,
                raw_text=raw,
            ))
        return results

    # --- 1. DIRECT REGEX MATCHES (High Confidence) ---
    # Patterns like "open X", "switch to X", "type X" should hit first.

    # Pattern: "switch to discord", "go to chrome"
    # Pattern: "switch to discord", "focus on chrome" (NO "go to" here to avoid folder ambiguity)
    switch_match = _R["switch_fast"].match(raw)
    if switch_match:
        app = _clean_app_name(switch_match.group(1))
        if app not in ("window", "app", "tab"):
            return [
                IntentResult(
                    "pc_action", "pc", app,
                    {"operation": "switch_window", "target": app, "safety_level": "safe"},
                    0.96, raw,
                )
            ]



    # Pattern: "type Hello World"
    dictation_match = _R["type_fast"].match(raw)
    if dictation_match:
        content = dictation_match.group(1).strip()
        return [
            IntentResult(
                "pc_action", "pc", "",
                {"operation": "type", "text": content, "safety_level": "safe"},
                0.98, raw,
            )
        ]

    # Pattern: "summarize this", "give me a summary"
    if "summarize" in t or "summary" in t:
        return [
            IntentResult("summarize", "browser", "current_page", {"style": "bullet"}, 0.95, raw)
        ]

    # Pattern: "remind me in 10 minutes to check the oven"
    remind_match = _R["remind"].match(raw)
    if remind_match:
        amount = int(remind_match.group(1))
        unit = remind_match.group(2).lower()
        text = remind_match.group(3).strip()
        if "second" in unit or "sec" in unit:
            delay = amount
        elif "minute" in unit or "min" in unit:
            delay = amount * 60
        elif "hour" in unit or "hr" in unit:
            delay = amount * 3600
        else:
            delay = 60
        return [
            IntentResult(
                "reminder", "pc", "",
                {"text": text, "delay_seconds": delay, "safety_level": "safe"},
                0.98, raw,
            )
        ]

    # Keep common "open X and search Y" commands on the pure-Python path.
    open_search = _R["open_search"].match(raw)
    if open_search:
        app = _clean_app_name(open_search.group(1))
        query = open_search.group(2).strip(" .")
        return [
            IntentResult(
                "browser_action",
                app,
                "",
                {
                    "goal": f"search for {query}",
                    "action": "search",
                    "query": query,
                    "max_steps": 1,
                },
                0.95,
                raw,
            ),
        ]

    # --- 2. COMPLEXITY CHECK ---
    # If the command contains multiple steps (conjunctions), 
    # force it to the Full Planner or Teach Mode.
    if any(conn in t for conn in [" and ", " then ", " after that ", " then ", " then "]):
        logger.info("Complex command detected (conjunctions) — passing to Full Planner.")
        return []

    open_search = _R["open_search"].match(raw)
    if open_search:
        app = _clean_app_name(open_search.group(1))
        query = open_search.group(2).strip(" .")
        return [
            IntentResult(
                "browser_action",
                app,
                "",
                {
                    "goal": f"search for {query}",
                    "action": "search",
                    "query": query,
                    "max_steps": 1,
                },
                0.95,
                raw,
            ),
        ]

    find_page_match = _R["find_page"].match(raw)
    if find_page_match:
        text_to_find = find_page_match.group(1).strip(" .")
        return [
            IntentResult(
                "pc_action",
                "pc",
                text_to_find,
                {"operation": "find_on_page", "text": text_to_find, "safety_level": "safe"},
                0.95,
                raw,
            )
        ]

    find_my_match = _R["find_my"].match(raw)
    if find_my_match and not find_page_match:
        query = find_my_match.group(1).strip()
        if len(query) > 2:
            return [
                IntentResult(
                    "pc_action", "pc", query,
                    {"operation": "find_file", "query": query, "safety_level": "safe"},
                    0.92, raw,
                )
            ]

    plain_search = _R["plain_search"].match(raw)
    if plain_search:
        query = plain_search.group(1).strip(" .")
        app_suffix = plain_search.group(2)
        if app_suffix:
            app = _clean_app_name(app_suffix)
            return [
                IntentResult(
                    "browser_action", app, "",
                    {"goal": f"search for {query} on {app}", "action": "search", "query": query, "max_steps": 1},
                    0.95, raw,
                )
            ]
        
        # Check if the query itself starts with an app name (e.g. "youtube lo-fi music")
        words = query.split()
        if len(words) == 1 and words[0] in ("youtube", "github", "reddit", "amazon"):
            app = words[0]
            return [IntentResult("open_app", app, app, {}, 0.92, raw)]

        if len(words) > 1 and (words[0] in DESKTOP_APPS or words[0] in ("youtube", "github", "reddit", "amazon")):
            app = words[0]
            real_query = " ".join(words[1:])
            return [
                IntentResult(
                    "browser_action", app, "",
                    {"goal": f"search for {real_query} on {app}", "action": "search", "query": real_query, "max_steps": 1},
                    0.93, raw,
                )
            ]

        return [
            IntentResult(
                "browser_action", "google", "",
                {"goal": f"search for {query} on google", "action": "search", "query": query, "max_steps": 1},
                0.95, raw,
            )
        ]
    # 3. Ordinal Browser Click (Reflex)
    ordinal_match = _R["ordinal_click"].match(raw)
    if ordinal_match:
        ordinal = ordinal_match.group(1).lower()
        target = ordinal_match.group(2).strip()
        return [
            IntentResult(
                "browser_action", "current", "",
                {"goal": f"click the {ordinal} {target}", "action": "click", "ordinal": ordinal, "target": target},
                0.96, raw,
            )
        ]

    message_match = _R["send_message"].match(raw)
    if message_match:
        verb = message_match.group(1).lower()
        target = message_match.group(2).strip(" .")
        message = message_match.group(3).strip()
        app = "whatsapp" if "whatsapp" in t else "gmail" if any(k in t for k in ["email", "mail", "gmail"]) else "whatsapp"
        return [
            IntentResult(
                "send_message",
                app,
                target,
                {"message": message, "draft_only": verb != "send"},
                0.94,
                raw,
            )
        ]

    # --- Conversational Reflexes ---
    chat_patterns = {
        _R["chat_wake"]: "wake_routine",
        _R["chat_greeting"]: "greeting",
        _R["chat_identity"]: "identity",
        _R["chat_status"]: "status",
        _R["chat_voice_desc"]: "voice_description",
        _R["chat_gratitude"]: "gratitude",
    }
    for pattern, topic in chat_patterns.items():
        if pattern.match(t):
            return [
                IntentResult(
                    "chat",
                    "jarvis",
                    "",
                    {"topic": topic, "response_style": "concise"},
                    0.99,
                    raw,
                )
            ]

    # --- Chat / Writing Reflexes ---
    chat_reflex_match = _R["chat_reflex"].match(raw)
    if chat_reflex_match:
        trigger = chat_reflex_match.group(1).lower()
        content = chat_reflex_match.group(2).strip()
        mode = "reply" if "reply" in trigger or "back" in trigger else "correct" if "correct" in trigger else "draft"
        return [
            IntentResult(
                "chat_reflex",
                "pc",
                "",
                {"mode": mode, "text": content, "safety_level": "safe"},
                0.98,
                raw,
            )
        ]

    pc_reflexes = {
        # --- Window Management ---
        "minimize": ("minimize_window", {}),
        "minimize window": ("minimize_window", {}),
        "minimise": ("minimize_window", {}),
        "maximize": ("maximize_window", {}),
        "maximize window": ("maximize_window", {}),
        "maximise": ("maximize_window", {}),
        "close window": ("close_window", {}),
        "close app": ("close_window", {}),
        "exit": ("close_window", {}),
        "switch window": ("switch_window", {}),
        "switch app": ("switch_window", {}),
        "alt tab": ("switch_window", {}),
        "snap left": ("snap_left", {}),
        "snap right": ("snap_right", {}),
        "snap window left": ("snap_left", {}),
        "snap window right": ("snap_right", {}),
        "show desktop": ("open_desktop", {}),
        "hide everything": ("open_desktop", {}),
        "desktop": ("open_desktop", {}),
        "take a screenshot": ("screenshot", {}),
        "take screenshot": ("screenshot", {}),
        "screenshot": ("screenshot", {}),

        # --- System Controls ---
        "increase brightness": ("brightness_up", {}),
        "brightness up": ("brightness_up", {}),
        "decrease brightness": ("brightness_down", {}),
        "brightness down": ("brightness_down", {}),

        # --- Browser Control (Ninja) ---
        "new tab": ("new_tab", {}),
        "open new tab": ("new_tab", {}),
        "close tab": ("close_tab", {}),
        "close current tab": ("close_tab", {}),
        "reopen tab": ("reopen_closed_tab", {}),
        "undo close tab": ("reopen_closed_tab", {}),
        "duplicate tab": ("duplicate_tab", {}),
        "next tab": ("next_tab", {}),
        "previous tab": ("prev_tab", {}),
        "reload": ("reload", {}),
        "refresh": ("reload", {}),
        "refresh page": ("reload", {}),
        "reload page": ("reload", {}),
        "hard reload": ("hard_reload", {}),
        "go back": ("browser_back", {}),
        "back": ("browser_back", {}),
        "go forward": ("browser_forward", {}),
        "forward": ("browser_forward", {}),
        "address bar": ("focus_address_bar", {}),
        "focus address bar": ("focus_address_bar", {}),
        "zoom in": ("zoom_in", {}),
        "zoom out": ("zoom_out", {}),
        "reset zoom": ("zoom_reset", {}),
        "copy url": ("copy_current_url", {}),
        "copy link": ("copy_current_url", {}),
        "inspect": ("inspect_element", {}),
        "inspect element": ("inspect_element", {}),
        "console": ("open_console", {}),
        "dev tools": ("open_console", {}),
        "history": ("show_history", {}),
        "bookmarks": ("show_bookmarks", {}),
        "downloads": ("show_downloads", {}),
        "incognito": ("open_incognito", {}),
        "private window": ("open_incognito", {}),

        # --- Instant Web Speed-Dial (Top 50+) ---
        "open youtube": ("launch_app", {"app": "", "url": "https://youtube.com"}),
        "open google": ("launch_app", {"app": "", "url": "https://google.com"}),
        "open amazon": ("launch_app", {"app": "", "url": "https://amazon.com"}),
        "open netflix": ("launch_app", {"app": "", "url": "https://netflix.com"}),
        "open facebook": ("launch_app", {"app": "", "url": "https://facebook.com"}),
        "open instagram": ("launch_app", {"app": "", "url": "https://instagram.com"}),
        "open reddit": ("launch_app", {"app": "", "url": "https://reddit.com"}),
        "open twitter": ("launch_app", {"app": "", "url": "https://twitter.com"}),
        "open x": ("launch_app", {"app": "", "url": "https://twitter.com"}),
        "open github": ("launch_app", {"app": "", "url": "https://github.com"}),
        "open chatgpt": ("launch_app", {"app": "", "url": "https://chat.openai.com"}),
        "open linkedin": ("launch_app", {"app": "", "url": "https://linkedin.com"}),
        "open wikipedia": ("launch_app", {"app": "", "url": "https://wikipedia.org"}),
        "open maps": ("launch_app", {"app": "", "url": "https://maps.google.com"}),
        "open gmail": ("launch_app", {"app": "", "url": "https://gmail.com"}),
        "open outlook": ("launch_app", {"app": "", "url": "https://outlook.com"}),
        "open discord web": ("launch_app", {"app": "", "url": "https://discord.com/app"}),
        "open spotify web": ("launch_app", {"app": "", "url": "https://open.spotify.com"}),
        "open twitch": ("launch_app", {"app": "", "url": "https://twitch.tv"}),
        "open stackoverflow": ("launch_app", {"app": "", "url": "https://stackoverflow.com"}),
        "open medium": ("launch_app", {"app": "", "url": "https://medium.com"}),
        "open quora": ("launch_app", {"app": "", "url": "https://quora.com"}),
        "open pinterest": ("launch_app", {"app": "", "url": "https://pinterest.com"}),
        "open ebay": ("launch_app", {"app": "", "url": "https://ebay.com"}),
        "open walmart": ("launch_app", {"app": "", "url": "https://walmart.com"}),
        "open apple": ("launch_app", {"app": "", "url": "https://apple.com"}),
        "open microsoft": ("launch_app", {"app": "", "url": "https://microsoft.com"}),
        "open yahoo": ("launch_app", {"app": "", "url": "https://yahoo.com"}),
        "open bing": ("launch_app", {"app": "", "url": "https://bing.com"}),
        "open duckduckgo": ("launch_app", {"app": "", "url": "https://duckduckgo.com"}),

        # --- Media & Sound ---
        "play": ("media_play_pause", {}),
        "pause": ("media_play_pause", {}),
        "play pause": ("media_play_pause", {}),
        "next": ("media_next", {}),
        "next track": ("media_next", {}),
        "next song": ("media_next", {}),
        "previous": ("media_previous", {}),
        "previous track": ("media_previous", {}),
        "previous song": ("media_previous", {}),
        "volume up": ("volume_up", {}),
        "increase volume": ("volume_up", {}),
        "louder": ("volume_up", {}),
        "volume down": ("volume_down", {}),
        "decrease volume": ("volume_down", {}),
        "quieter": ("volume_down", {}),
        "mute": ("volume_mute", {}),
        "unmute": ("volume_mute", {}),
        "mute sounds": ("volume_mute", {}),
        "turn off sound": ("volume_mute", {}),
        "stop sounds": ("volume_mute", {}),
        "fullscreen": ("fullscreen", {}),
        "full screen": ("fullscreen", {}),

        # --- Editing & Text ---
        "copy": ("copy", {}),
        "copy that": ("copy", {}),
        "paste": ("paste", {}),
        "paste that": ("paste", {}),
        "undo": ("undo", {}),
        "redo": ("redo", {}),
        "select all": ("select_all", {}),
        "save": ("save_file", {}),
        "save this": ("save_file", {}),
        "find": ("find_on_page", {}),
        "search on page": ("find_on_page", {}),
        "bold": ("text_bold", {}),
        "italic": ("text_italic", {}),

        # --- App Launchers (Instant) ---
        "open discord": ("launch_app", {"app": "discord"}),
        "open spotify": ("launch_app", {"app": "spotify"}),
        "open slack": ("launch_app", {"app": "slack"}),
        "open whatsapp": ("launch_app", {"app": "whatsapp"}),
        "open telegram": ("launch_app", {"app": "telegram"}),
        "open vscode": ("launch_app", {"app": "vscode"}),
        "open code": ("launch_app", {"app": "vscode"}),
        "open terminal": ("launch_app", {"app": "terminal"}),
        "open cmd": ("launch_app", {"app": "cmd"}),
        "open powershell": ("launch_app", {"app": "powershell"}),
        "open notepad": ("launch_app", {"app": "notepad"}),
        "open calculator": ("launch_app", {"app": "calculator"}),
        "open paint": ("launch_app", {"app": "paint"}),
        "open notion": ("launch_app", {"app": "", "url": "https://notion.so"}),
        "open perplexity": ("launch_app", {"app": "", "url": "https://perplexity.ai"}),
        "open claude": ("launch_app", {"app": "", "url": "https://claude.ai"}),
        "open gemini": ("launch_app", {"app": "", "url": "https://gemini.google.com"}),
        "open figma": ("launch_app", {"app": "", "url": "https://figma.com"}),
        "display settings": ("launch_app", {"app": "ms-settings:display"}),
        "wifi settings": ("launch_app", {"app": "ms-settings:network-wifi"}),
        "bluetooth settings": ("launch_app", {"app": "ms-settings:bluetooth"}),

        # --- System Folders ---
        "open desktop folder": ("open_desktop", {}),
        "open downloads": ("open_downloads", {}),
        "open documents": ("open_documents", {}),
        "open pictures": ("open_pictures", {}),
        "open videos": ("open_videos", {}),
        "open music": ("open_music", {}),
        "task manager": ("open_task_manager", {}),
        "settings": ("open_settings", {}),
        "control panel": ("open_settings", {}),
        "lock pc": ("lock_pc", {}),
        "lock screen": ("lock_pc", {}),

        # --- Navigation Shortcuts ---
        "scroll down": ("scroll_down", {}),
        "scroll up": ("scroll_up", {}),
        "page down": ("page_down", {}),
        "page up": ("page_up", {}),
        "home": ("go_to_top", {}),
        "end": ("go_to_bottom", {}),
        "top of page": ("go_to_top", {}),
        "bottom of page": ("go_to_bottom", {}),

        # --- Dev & System Aliases ---
        "open python": ("launch_app", {"app": "terminal", "command": "python"}),
        "open node": ("launch_app", {"app": "terminal", "command": "node"}),
        "open monitor": ("open_task_manager", {}),
        "system info": ("open_settings", {"page": "about"}),
        "open camera": ("launch_app", {"app": "camera"}),
        "open photos": ("open_pictures", {}),
        "open movies": ("open_videos", {}),
        "open files": ("open_documents", {}),

        # --- Work & Productivity ---
        "open teams": ("launch_app", {"app": "teams"}),
        "open zoom": ("launch_app", {"app": "zoom"}),
        "open jira": ("launch_app", {"app": "", "url": "https://atlassian.net"}),
        "open trello": ("launch_app", {"app": "", "url": "https://trello.com"}),
        "open calendar": ("launch_app", {"app": "", "url": "https://calendar.google.com"}),
        "open sheets": ("launch_app", {"app": "", "url": "https://sheets.new"}),
        "open docs": ("launch_app", {"app": "", "url": "https://docs.new"}),
        "open slides": ("launch_app", {"app": "", "url": "https://slides.new"}),

        # --- Entertainment & Gaming ---
        "open steam": ("launch_app", {"app": "steam"}),
        "open disney plus": ("launch_app", {"app": "", "url": "https://disneyplus.com"}),
        "open hulu": ("launch_app", {"app": "", "url": "https://hulu.com"}),
        "open prime video": ("launch_app", {"app": "", "url": "https://primevideo.com"}),
        "open epic games": ("launch_app", {"app": "epicgames"}),

        # --- Utilities & Info ---
        "open speedtest": ("launch_app", {"app": "", "url": "https://speedtest.net"}),
        "open translate": ("launch_app", {"app": "", "url": "https://translate.google.com"}),
        "open weather": ("launch_app", {"app": "", "url": "https://weather.com"}),
        "open stocks": ("launch_app", {"app": "", "url": "https://finance.yahoo.com"}),
        "open crypto": ("launch_app", {"app": "", "url": "https://coinmarketcap.com"}),
        "open news": ("launch_app", {"app": "", "url": "https://news.google.com"}),

        # --- Power User Utilities ---
        "device manager": ("launch_app", {"app": "devmgmt.msc"}),
        "registry editor": ("launch_app", {"app": "regedit"}),
        "disk cleanup": ("launch_app", {"app": "cleanmgr"}),
        "resource monitor": ("launch_app", {"app": "resmon"}),
        "system properties": ("launch_app", {"app": "control", "args": "sysdm.cpl"}),

        # --- File & Clipboard (Premium) ---
        "clipboard history": ("hotkey", {"keys": ["win", "v"]}),
        "show clipboard": ("hotkey", {"keys": ["win", "v"]}),
        "recent files": ("open_recent", {}),
        "recent documents": ("open_recent", {}),

        # --- Shell Folders ---
        "open recycle bin": ("launch_app", {"app": "shell:RecycleBinFolder"}),
        "open this pc": ("launch_app", {"app": "shell:MyComputerFolder"}),

        # --- System Info ---
        "who am i": ("get_current_user", {}),
        "current user": ("get_current_user", {}),
        "who is logged in": ("get_current_user", {}),
        "my ip": ("get_ip_address", {}),
        "ip address": ("get_ip_address", {}),
        "what is my ip": ("get_ip_address", {}),
        "screen resolution": ("get_screen_resolution", {}),

        # --- Utilities ---
        "empty recycle bin": ("empty_recycle_bin", {}),
        "empty trash": ("empty_recycle_bin", {}),
        "take a break": ("break_timer", {}),

        # --- Display ---
        "night light": ("toggle_night_light", {}),
        "blue light": ("toggle_night_light", {}),
        "focus mode": ("toggle_focus_assist", {}),
        "do not disturb": ("toggle_focus_assist", {}),

        # --- System Status (Premium) ---
        "check battery": ("get_battery_status", {}),
        "battery level": ("get_battery_status", {}),
        "how is my battery": ("get_battery_status", {}),
        "what time is it": ("get_current_time", {}),
        "current time": ("get_current_time", {}),
        "today's date": ("get_current_date", {}),
        "how is the pc": ("get_system_health", {}),
        "system health": ("get_system_health", {}),
        "cpu usage": ("get_system_health", {}),
    }
    def _reflex_result(operation: str, extra: dict, confidence: float) -> IntentResult:
        if operation == "browser_action":
            return IntentResult(
                "browser_action",
                "browser",
                "",
                {"safety_level": "safe", **extra},
                confidence,
                raw,
            )
        return IntentResult(
            "pc_action",
            "pc",
            "",
            {"operation": operation, "safety_level": "safe", **extra},
            confidence,
            raw,
        )

    if t in pc_reflexes:
        operation, extra = pc_reflexes[t]
        result = _reflex_result(operation, extra, 0.96)
        return [_apply_context(result, _CURRENT_CONTEXT)]

    # --- Plugin Reflexes ---
    from core.plugin_manager import get_plugin_manager
    _plugin_reflexes = get_plugin_manager().get_reflex_keys()
    if t in _plugin_reflexes:
        operation, extra = _plugin_reflexes[t]
        result = _reflex_result(operation, extra, 0.96)
        return [_apply_context(result, _CURRENT_CONTEXT)]

    # --- Learned Reflexes (Teach Mode) ---
    learned = _load_learned_reflexes()
    if t in learned:
        entry = learned[t].copy()
        operation = entry.pop("operation", "launch_app")
        result = IntentResult("pc_action", "pc", "", {"operation": operation, "safety_level": "safe", **entry}, 0.95, raw)
        return [_apply_context(result, _CURRENT_CONTEXT)]

    unsupported_reflexes = {
        "pin tab", "mute tab", "unmute tab", "reader mode",
        "sleep", "restart", "shutdown",
    }
    if t in unsupported_reflexes:
        return []

    # --- Fuzzy Matching ---
    all_keys = list(pc_reflexes.keys()) + list(learned.keys()) + list(_plugin_reflexes.keys())
    fuzzy_hit = _fuzzy_match(t, all_keys)
    if fuzzy_hit:
        if fuzzy_hit in pc_reflexes:
            operation, extra = pc_reflexes[fuzzy_hit]
        elif fuzzy_hit in _plugin_reflexes:
            operation, extra = _plugin_reflexes[fuzzy_hit]
        else:
            entry = learned[fuzzy_hit].copy()
            operation = entry.pop("operation", "launch_app")
            extra = entry
        result = _reflex_result(operation, extra, 0.85)
        return [_apply_context(result, _CURRENT_CONTEXT)]

    switch_match = _R["switch_url"].match(raw)
    if switch_match:
        app = _clean_app_name(switch_match.group(1))
        # If it looks like a URL, navigate there instead of switching windows
        if "." in app and not app.endswith(" "):
            return [
                IntentResult(
                    "open_app", app, app, {}, 0.96, raw,
                )
            ]
        return [
            IntentResult(
                "pc_action",
                "pc",
                app,
                {"operation": "switch_window", "target": app, "safety_level": "safe"},
                0.96,
                raw,
            )
        ]

    launch_match = _R["launch"].match(raw)
    if launch_match:
        app = _clean_app_name(launch_match.group(1))
        # If it looks like a URL, open it directly
        if "." in app and not app.endswith(" "):
            return [
                IntentResult(
                    "open_app", app, app, {}, 0.96, raw,
                )
            ]
        # Known common local executables
        common_apps = (
            "notepad", "calculator", "paint", "cmd", "terminal", "powershell", 
            "code", "vscode", "discord", "spotify", "chrome", "edge", "brave", 
            "word", "excel", "powerpoint", "outlook", "teams", "zoom", "obs", "steam"
        )
        if app in common_apps:
            return [
                IntentResult(
                    "pc_action",
                    app,
                    app,
                    {"operation": "launch_app", "app": app, "safety_level": "safe"},
                    0.96,
                    raw,
                )
            ]
        else:
            # Fallback to Google Search if it's an unknown app/website
            return [
                IntentResult(
                    "browser_action", 
                    "google", 
                    "",
                    {"goal": f"search for {app} on google", "action": "search", "query": app, "max_steps": 1},
                    0.90, 
                    raw,
                )
            ]

    # Pattern: [verb] [target] [type] -> "open games folder"
    file_type_suffix = _R["file_type_suffix"].match(raw)
    # Pattern: [verb] [type] [target] -> "open folder games"
    file_type_prefix = _R["file_type_prefix"].match(raw)
    
    match = file_type_suffix or file_type_prefix
    if match:
        target = match.group(1).strip(" .")
        verb = t.split()[0]
        operation = "open_file" if verb in ("open", "launch", "show") else "find_file"
        return [
            IntentResult(
                "pc_action", "pc", target,
                {"operation": operation, "path": target, "query": target, "safety_level": "safe"},
                0.98, raw,
            )
        ]


    screenshot_match = _R["screenshot"].match(raw)
    if screenshot_match:
        return [IntentResult("pc_action", "pc", "", {"operation": "screenshot", "safety_level": "safe"}, 0.95, raw)]

    download_match = _R["download"].match(raw)
    if download_match:
        return [
            IntentResult(
                "browser_action",
                "browser",
                "",
                {"goal": "download the item", "action": "auto", "max_steps": 3},
                0.98,
                raw,
            )
        ]

    paste_folder_match = _R["paste_folder"].match(raw)
    if paste_folder_match:
        folder = paste_folder_match.group(1).strip()
        return [
            IntentResult(
                "pc_action",
                "pc",
                folder,
                {"operation": "paste", "path": folder, "safety_level": "safe"},
                0.98,
                raw,
            )
        ]

    paste_match = _R["paste"].match(raw)
    if paste_match:
        text_to_paste = (paste_match.group(1) or "").strip()
        return [
            IntentResult(
                "pc_action",
                "pc",
                text_to_paste,
                {"operation": "paste", "text": text_to_paste, "safety_level": "safe"},
                0.95,
                raw,
            )
        ]

    copy_match = _R["copy"].match(raw)
    if copy_match:
        text_to_copy = (copy_match.group(1) or "").strip()
        return [
            IntentResult(
                "pc_action",
                "pc",
                text_to_copy,
                {"operation": "copy", "text": text_to_copy, "safety_level": "safe"},
                0.95,
                raw,
            )
        ]

    rename_match = _R["rename_dual"].match(raw)
    if not rename_match:
        rename_match = _R["rename_single"].match(raw)
    
    if rename_match:
        # If it was the two-part match, group 2 is the new name. If it was the fallback, group 1 is the new name.
        if rename_match.lastindex == 2:
            new_name = rename_match.group(2).strip(" .")
        else:
            new_name = rename_match.group(1).strip(" .")
        return [
            IntentResult(
                "pc_action", "pc", new_name,
                {
                    "operation": "rename_file",
                    "new_name": new_name,
                    "safety_level": "confirm",
                    "requires_confirmation": True,
                },
                0.96, raw,
            )
        ]

    vision_match = _R["describe_screen"].match(raw)
    if vision_match:
        return [IntentResult("describe_screen", "pc", "", {"query": "describe the whole screen"}, 0.98, raw)]

    switch_match = _R["switch_generic"].match(raw)
    if switch_match:
        return [IntentResult("pc_action", "pc", "", {"operation": "switch_window", "safety_level": "safe"}, 0.94, raw)]

    guarded_match = _R["guarded"].match(raw)
    if guarded_match:
        verb = guarded_match.group(1).lower()
        target = guarded_match.group(2).strip()
        operation = "shell" if verb == "run command" else verb
        safety = "forbidden" if operation in ("shell", "install") else "confirm"
        return [
            IntentResult(
                "pc_action",
                "pc",
                target,
                {
                    "operation": operation,
                    "target": target,
                    "safety_level": safety,
                    "requires_confirmation": safety == "confirm",
                },
                0.9,
                raw,
            )
        ]

    open_it_match = _R["open_that"].match(raw)
    if open_it_match:
        return [
            IntentResult(
                "pc_action",
                "pc",
                "",
                {"operation": "open_file", "path": "screenshot.png", "safety_level": "safe"},
                0.98,
                raw,
            )
        ]

    open_only = _R["open_only"].match(raw)
    if open_only:
        app = _clean_app_name(open_only.group(1))
        if app in DESKTOP_APPS:
            return [
                IntentResult(
                    "pc_action",
                    app,
                    app,
                    {"operation": "launch_app", "app": app, "safety_level": "safe"},
                    0.96,
                    raw,
                )
            ]
        return [IntentResult("open_app", app, app, {}, 0.98, raw)]

    type_match = _R["type_only"].match(raw)
    if type_match:
        value = type_match.group(1).strip()
        return [
            IntentResult(
                "pc_action",
                "pc",
                "",
                {"operation": "type", "text": value, "safety_level": "safe"},
                0.92,
                raw,
            )
        ]

    click_match = _R["click"].match(raw)
    if click_match:
        target = click_match.group(1).strip(" .")
        key_targets = {"enter", "tab", "escape", "backspace"}
        if target.lower() not in key_targets:
            return [
                IntentResult(
                    "browser_action",
                    "browser",
                    "",
                    {"goal": f"click {target}", "action": "click", "labels": [target], "max_steps": 1},
                    0.92,
                    raw,
                )
            ]

    key_aliases = {
        "enter": "Enter",
        "press enter": "Enter",
        "escape": "Escape",
        "press escape": "Escape",
        "tab": "Tab",
        "press tab": "Tab",
    }
    if t in key_aliases:
        key = key_aliases[t]
        return [
            IntentResult(
                "pc_action",
                "pc",
                "",
                {"operation": "press", "key": key, "safety_level": "safe"},
                0.95,
                raw,
            )
        ]

    return []


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


def _extract_json_array(text: str) -> list[dict]:
    cleaned = re.sub(r"```(?:json)?", "", text).strip().strip("`")
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.S | re.I).strip()
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        pass

    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start:end + 1])

    objects = _extract_json_objects(cleaned)
    if objects:
        return objects
    raise json.JSONDecodeError("No JSON array found", cleaned, 0)


# ── Ollama planner (non-streaming fallback) ───────────────────────────────

def _plan_ollama(text: str, context: Context) -> Generator[IntentResult, None, None]:
    """
    Call Ollama and parse the full array response.
    Ollama streaming for JSON arrays is unreliable, so we wait for
    the full response then yield steps quickly.
    """
    user_msg = _build_user_message(text, context)
    
    # ── MULTIMODAL PLANNING (Ollama) ────────────────────────────────────
    payload = {
        "model": _resolve_ollama_model(),
        "messages": [
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "stream": False,
        "format": "json",
        "keep_alive": "10m",
        "options": {
            "temperature": 0.0, 
            "num_predict": 128, 
            "num_ctx": 1024,   # Reduced context for 2GB RAM survival
            "num_thread": 4    # Limit background threads to save memory
        },
    }

    # If model is vision-capable and we have a screenshot, attach it
    shot_path = context.dom.get("screenshot") if context.dom else None
    if "vision" in OLLAMA_MODEL.lower() and shot_path and os.path.exists(shot_path):
        import base64
        with open(shot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")
        # Ollama expects 'images' field at the message level or root depending on API version
        # For /api/chat, it's typically inside the message
        payload["messages"][-1]["images"] = [img_b64]

    resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=60)
    resp.raise_for_status()

    content = resp.json().get("message", {}).get("content", "")
    logger.info(f"RAW OLLAMA: {content}")

    steps_raw = _extract_json_array(content)
    for i, raw in enumerate(steps_raw, 1):
        step = _parse_step(raw)
        logger.info(f"Plan step {i}: {step.intent} → {step.app} [{step.target}]")
        yield step


# ── Public API ────────────────────────────────────────────────────────────

class Planner:
    def __init__(self, model: str = None):
        self.model = model or OLLAMA_MODEL
        self.custom_system_prompt = None

    def set_persona(self, system_prompt: str):
        self.custom_system_prompt = system_prompt

    def list_reflexes(self) -> list[str]:
        """Returns a summary of supported rule-based triggers."""
        return [
            "Browser: Open [app], Search [query], Click the [Nth] [element], Navigation, Tabs",
            "PC: Launch [app], Open [file/folder], Minimize/Maximize, Switch, Screenshot",
            "Text: Type/Dictate: [text], Correct/Reply: [text], Copy/Paste",
            "Media: Play/Pause, Next/Prev, Volume Up/Down/Mute",
            "Chat: Greetings, Identity, Help, Describe my voice"
        ]

    def can_fast_plan(self, text: str) -> bool:
        return bool(_fast_plan(text))

    def plan(self, text: str, context: Context) -> Generator[IntentResult, None, None]:
        global _CURRENT_CONTEXT
        _CURRENT_CONTEXT = context
        start = time.time()
        
        # ── DIRECT SMART DICTATION OVERRIDE ──
        # Handles "dictate in [app]" (targeted dictation mode, no text)
        dictate_in = re.match(r'^dictate\s+in\s+([a-zA-Z0-9\s]{2,20})$', text.strip(), re.I)
        if dictate_in:
            app = dictate_in.group(1).strip().lower()
            yield IntentResult("pc_action", app, app, {"operation": "launch_app", "app": app, "safety_level": "safe"}, 0.99, text)
            yield IntentResult("dictation_mode", "pc", "", {"operation": "start", "safety_level": "safe"}, 0.99, text)
            return

        # Handles "type [text]" AND "type [text] in [app]"
        dictate_match = re.match(r'^(?:dictate|type)\s+(.*?)(?:\s+in\s+([a-zA-Z0-9\s]{2,20}))?$', text.strip(), re.IGNORECASE)
        if dictate_match:
            content = dictate_match.group(1).strip()
            app = (dictate_match.group(2) or "").strip().lower()
            
            if content.lower().startswith("out "):
                content = content[4:]

            # Validate that the app is an actual application name to avoid matching "type I am in London"
            valid_apps = {"discord", "whatsapp", "chrome", "notepad", "slack", "teams", "telegram", "word", "browser", "edge"}
            is_valid_app = any(app == a or app.endswith(a) for a in valid_apps)

            if app and is_valid_app:
                # 1. Switch to the app
                yield IntentResult("pc_action", app, app, {"operation": "launch_app", "app": app, "safety_level": "safe"}, 0.99, text)
                
                # 2. Check TeachMode for a focus workflow (e.g. user taught JARVIS where to click)
                from core.teach_mode import get_teach_mode
                tm = get_teach_mode()
                focus_workflow = tm.find_workflow(f"focus {app}") or tm.find_workflow(f"{app} chat") or tm.find_workflow(f"click {app}")
                
                if focus_workflow:
                    logger.info(f"Found taught focus workflow for '{app}'. Executing clicks before typing.")
                    for step in focus_workflow["steps"]:
                        yield IntentResult(
                            intent=step.get("intent", "pc_action"),
                            app=step.get("app", "pc"),
                            target=step.get("target", ""),
                            data=step.get("data", {}),
                            confidence=0.97,
                            raw_text=text,
                        )
                else:
                    logger.info(f"No taught focus workflow found for '{app}'. Assuming app auto-focuses the text box.")

            # 3. Type the text
            yield IntentResult("pc_action", "pc", "", {"operation": "type", "text": content, "safety_level": "safe"}, 0.99, text)
            return

        # ── STEP 1: PYTHON SPLITTER (Direct Logic) ──
        direct_steps = list(_fast_plan(text))
        is_command_list = bool(re.search(r"[,;]|\bthen\b|\bafter that\b", text, re.I))
        if direct_steps and not is_command_list:
            logger.info(f"Direct reflex matched: {text}")
            yield from direct_steps
            return

        raw_commands = re.split(r'\s*(?:[,;]|\band\b|\bthen\b|\bafter that\b)\s*', text, flags=re.IGNORECASE)
        
        for cmd in raw_commands:
            cmd = cmd.strip()
            if not cmd: continue
            logger.info(f"Planning piece: '{cmd}'")
            
            # Strip internal state flags for routing
            t = cmd.lower()
            for flag in ["browser_selected", "visibility_selected", "use_api", "use_local"]:
                t = t.replace(flag, "").strip()
            
            # ── STEP 0.5: SMART SITE ACTIONS (Highest Speed Reflexes) ──
            # Verbs: search, find, look up, watch, play, buy, research, check, go to
            # Sites (Direct): youtube, google, amazon, wikipedia, twitter, reddit, github, bing, duckduckgo, ebay, netflix, spotify, hulu, disney, prime, steam, epic, apple, microsoft, facebook, instagram
            smart_action_match = re.match(r'^(?:search|find|look up|watch|play|buy|research|check|go to|navigate to)\s+(.+?)\s+on\s+(youtube|google|amazon|wikipedia|twitter|reddit|github|bing|duckduckgo|ebay|netflix|spotify|hulu|disney|prime|steam|epic|apple|microsoft|facebook|instagram)$', t, re.I)
            if smart_action_match:
                query = smart_action_match.group(1).strip()
                site = smart_action_match.group(2).strip().lower()
                
                site_urls = {
                    "youtube": "https://www.youtube.com/results?search_query=",
                    "google": "https://www.google.com/search?q=",
                    "amazon": "https://www.amazon.com/s?k=",
                    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search=",
                    "twitter": "https://twitter.com/search?q=",
                    "reddit": "https://www.reddit.com/search/?q=",
                    "github": "https://github.com/search?q=",
                    "bing": "https://www.bing.com/search?q=",
                    "duckduckgo": "https://duckduckgo.com/?q=",
                    "ebay": "https://www.ebay.com/sch/i.html?_nkw=",
                    "netflix": "https://www.netflix.com/search?q=",
                    "spotify": "https://open.spotify.com/search/",
                    "hulu": "https://www.hulu.com/search?q=",
                    "disney": "https://www.disneyplus.com/search?q=",
                    "prime": "https://www.amazon.com/s?k=",
                    "steam": "https://store.steampowered.com/search/?term=",
                    "epic": "https://www.epicgames.com/store/en-US/browse?q=",
                    "apple": "https://www.apple.com/us/search/",
                    "microsoft": "https://www.microsoft.com/en-us/search/explore?q=",
                    "facebook": "https://www.facebook.com/search/top/?q=",
                    "instagram": "https://www.instagram.com/explore/tags/"
                }
                
                base_url = site_urls.get(site, "https://www.google.com/search?q=")
                url = f"{base_url}{requests.utils.quote(query)}"
                yield IntentResult("browser_action", "browser", url, {"action": "navigate", "url": url, "goal": f"{cmd} directly"}, 0.98, cmd)
                continue

            # ── STEP 1.5: FAST REFLEX CHECK (Pure Python, No AI) ──
            # This handles all system commands, open apps, and taught workflows instantly.
            fast_steps = list(_fast_plan(cmd))
            if fast_steps:
                logger.info(f"Reflex matched: {cmd}")
                yield from fast_steps
                continue

            # ── STEP 2: BRAIN ROUTER (Task Detection) ──
            from core.brain_router import detect_task_type, call_model
            task_type = detect_task_type(cmd)
            
            if task_type != "general":
                # Option 1: Interactive Mode - Ask the user
                if os.getenv("JARVIS_INTERACTIVE", "false").lower() == "true":
                    # Step A: Visibility Decision (If browser was already selected)
                    if "BROWSER_SELECTED" in cmd and "VISIBILITY_SELECTED" not in cmd:
                        yield IntentResult("chat_reflex", "pc", "", {
                            "mode": "decision_prompt", 
                            "text": "How should I run the browser?",
                            "options": ["Stealth Mode (Background)", "Watch Jarvis (Visual)"],
                            "task_type": "browser_visibility",
                            "original_cmd": cmd + " VISIBILITY_SELECTED"
                        }, 1.0, cmd)
                        return

                    # Step B: Brain Decision (If no choice made yet)
                    if "BROWSER_SELECTED" not in cmd and "USE_API" not in cmd and "USE_LOCAL" not in cmd:
                        yield IntentResult("chat_reflex", "pc", "", {
                            "mode": "decision_prompt", 
                            "text": f"I've detected a {task_type} task. How should I handle it?",
                            "options": ["Local (Free/Offline)", "API (Fast/Premium)", "Browser (Free/Automation)"],
                            "task_type": task_type
                        }, 1.0, cmd)
                        return

                logger.info(f"Specialized task detected: {task_type}. Consulting Brain Router...")
                brain_response = call_model(task_type, "You are a professional assistant.", cmd)
                
                if brain_response and "[BROWSER AUTOMATION TRIGGERED]" in brain_response:
                    # Expand Browser AI into a physical multi-step sequence
                    from core.brain_router import get_model_for_task
                    config = get_model_for_task(task_type)
                    model_id = config["model"].lower()
                    
                    urls = {
                        # LLMs & Search
                        "chatgpt": "https://chatgpt.com",
                        "claude": "https://claude.ai",
                        "gemini": "https://gemini.google.com",
                        "perplexity": "https://perplexity.ai",
                        "grok": "https://x.com/i/grok",
                        "poe": "https://poe.com",
                        "pi": "https://pi.ai",
                        "huggingface": "https://huggingface.co/chat",
                        "you": "https://you.com",
                        "copilot": "https://bing.com/chat",
                        "mistral": "https://chat.mistral.ai",
                        "deepseek": "https://chat.deepseek.com",
                        "phind": "https://phind.com",
                        "komo": "https://komo.ai",
                        "andi": "https://andisearch.com",
                        "perplexity_labs": "https://labs.perplexity.ai",
                        
                        # Writing & Productivity
                        "jasper": "https://jasper.ai",
                        "copyai": "https://copy.ai",
                        "writesonic": "https://writesonic.com",
                        "rytr": "https://rytr.me",
                        "wordtune": "https://wordtune.com",
                        "quillbot": "https://quillbot.com",
                        "grammarly": "https://grammarly.com",
                        
                        # Image Generation
                        "midjourney": "https://discord.com/channels/@me",
                        "leonardo": "https://leonardo.ai",
                        "playground": "https://playground.com",
                        "lexica": "https://lexica.art",
                        "firefly": "https://firefly.adobe.com",
                        "canva": "https://canva.com",
                        "krea": "https://krea.ai",
                        "ideogram": "https://ideogram.ai",
                        
                        # Video Generation
                        "runway": "https://runwayml.com",
                        "pika": "https://pika.art",
                        "luma": "https://lumalabs.ai",
                        "kaiber": "https://kaiber.ai",
                        "heygen": "https://heygen.com",
                        "synthesia": "https://synthesia.io",
                        "sora": "https://openai.com/sora",
                        
                        # Audio & Music
                        "elevenlabs": "https://elevenlabs.io",
                        "suno": "https://suno.com",
                        "udio": "https://udio.com",
                        "beatoven": "https://beatoven.ai",
                        "soundraw": "https://soundraw.io",
                        "murf": "https://murf.ai",
                        
                        # Coding & Specialized
                        "replit": "https://replit.com",
                        "v0": "https://v0.dev",
                        "cursor": "https://cursor.sh",
                        "blackbox": "https://blackbox.ai",
                        "sourcegraph": "https://sourcegraph.com"
                    }
                    target_url = urls.get(model_id, f"https://www.google.com/search?q={model_id}")
                    
                    logger.info(f"Executing Multi-Step Browser AI Automation for {model_id}...")
                    yield IntentResult("browser_action", "browser", target_url, {"action": "navigate", "url": target_url}, 1.0, cmd)
                    yield IntentResult("pc_action", "pc", "", {"operation": "wait", "seconds": 4}, 1.0, cmd)
                    # For more complex 'Manus-like' autonomous interaction, we trigger the agent loop
                    yield IntentResult("browser_action", "browser", "", {"action": "agent_loop", "goal": f"Find the chat input box, type '{cmd}', and press enter."}, 1.0, cmd)
                    continue
                elif brain_response:
                    # If brain returned a text answer (like a script or email draft) or a hardware warning
                    yield IntentResult("chat_reflex", "pc", "", {"mode": "answer", "text": brain_response}, 1.0, cmd)
                    continue

            # ── STEP 3: FAST REFLEX CHECK (Pure Python, No AI) ──
            fast_steps = _fast_plan(cmd)
            if fast_steps:
                logger.info(f"Reflex matched: {cmd}")
                yield from fast_steps
                continue

            # ── STEP 3: SMART FALLBACK (Pure Python, No AI) ──
            fallback_steps = list(self._smart_fallback(cmd))
            if fallback_steps and fallback_steps[0].intent != "unknown":
                logger.info(f"Smart fallback matched: {cmd}")
                yield from fallback_steps
                continue


            # ── STEP 5: LLM (Optional, only if available) ──
            try:
                if LLM_PROVIDER == "ollama":
                    llm_steps = list(_plan_ollama(cmd, context))
                    # Auto-cache the LLM result so we never ask again
                    if llm_steps:
                        from core.teach_mode import get_teach_mode
                        step_dicts = [{"intent": s.intent, "app": s.app, "target": s.target, "data": s.data} for s in llm_steps]
                        get_teach_mode().save_llm_result(cmd, step_dicts)
                    yield from llm_steps
                else:
                    # No AI available - offer to learn
                    logger.info(f"No match and no AI for: '{cmd}' - suggesting teach mode")
                    yield IntentResult(
                        "chat_reflex", "pc", "",
                        {"mode": "teach_prompt", "text": f"I don't know '{cmd}' yet. You can teach me!", "safety_level": "safe"},
                        0.5, cmd,
                    )
            except (requests.ConnectionError, requests.Timeout):
                logger.warning(f"AI offline. Using smart fallback for: {cmd}")
                yield from self._smart_fallback(cmd)
            except Exception as e:
                logger.error(f"Error planning '{cmd}': {e}")
                yield from self._smart_fallback(cmd)

        logger.info(f"Total plan generation: {time.time() - start:.2f}s")

    def _smart_fallback(self, text: str) -> Generator[IntentResult, None, None]:
        """Powerful rule-based fallback. No AI needed."""
        t = text.lower().strip()
        raw = text.strip()

        # ── "Open X" (catch-all for any app/site) ──
        open_match = re.match(r'^(?:open|launch|start|go to|visit|navigate to)\s+(.+)$', t, re.I)
        if open_match:
            target = open_match.group(1).strip()
            # If it looks like a URL
            if '.' in target and ' ' not in target:
                url = target if target.startswith('http') else f"https://{target}"
                yield IntentResult("pc_action", "pc", target, {"operation": "launch_app", "app": "", "url": url, "safety_level": "safe"}, 0.90, raw)
                return
            # Otherwise treat as an app name
            yield IntentResult("pc_action", target, target, {"operation": "launch_app", "app": target, "safety_level": "safe"}, 0.85, raw)
            return

        # ── "Open X Folder/File" ──
        file_match = re.match(r'^(?:open|launch|show|find|search(?: for)?|go to)\s+(.+?)\s+(?:file|folder|document|dir|directory)$', t, re.I)
        if file_match:
            target = file_match.group(1).strip()
            # Map common names to shell shortcuts
            shell_map = {
                "documents": "shell:Personal",
                "downloads": "shell:Downloads",
                "pictures": "shell:My Pictures",
                "music": "shell:My Music",
                "videos": "shell:My Video",
                "desktop": "shell:Desktop",
            }
            path = shell_map.get(target, target)
            yield IntentResult("pc_action", "pc", target, {"operation": "launch_app", "app": "explorer", "args": path, "safety_level": "safe"}, 0.95, raw)
            return

        # ── "Search for X" / "Google X" / "Look up X" (Default to Google) ──
        search_match = re.match(r'^(?:search|google|look up|find|search for|google for)\s+(.+)$', t, re.I)
        if search_match:
            query = search_match.group(1).strip()
            yield IntentResult("browser_action", "google", query, {"action": "search", "query": query, "goal": f"search for {query}"}, 0.90, raw)
            return

        # ── "Click X" / "Press X" / "Select X" ──
        click_match = re.match(r'^(?:click|press|tap|select|hit)\s+(?:the\s+|on\s+)?(.+)$', t, re.I)
        if click_match:
            target = click_match.group(1).strip()
            yield IntentResult("browser_action", "browser", target, {"action": "click", "target": target, "goal": f"click {target}"}, 0.85, raw)
            return

        # ── "Type X" / "Enter X" ──
        type_match = re.match(r'^(?:type|enter|input)\s+(.+)$', t, re.I)
        if type_match:
            content = type_match.group(1).strip()
            yield IntentResult("pc_action", "pc", "", {"operation": "type", "text": content, "safety_level": "safe"}, 0.85, raw)
            return

        # ── "Send message" / "Text someone" ──
        msg_match = re.match(r'^(?:send|message|text|tell)\s+(.+)$', t, re.I)
        if msg_match:
            content = msg_match.group(1).strip()
            app = "whatsapp" if "whatsapp" in t else "gmail"
            yield IntentResult("send_message", app, "", {"message": content}, 0.70, raw)
            return

        # ── "Summarize" / "Summary" ──
        if "summarize" in t or "summary" in t:
            yield IntentResult("summarize", "browser", "current_page", {"style": "bullet"}, 0.80, raw)
            return

        # ── "Go to X" in browser (URL-like) ──
        goto_match = re.match(r'^(?:go to|navigate to|head to)\s+(.+)$', t, re.I)
        if goto_match:
            target = goto_match.group(1).strip()
            url = target if target.startswith('http') else f"https://{target}"
            yield IntentResult("browser_action", "browser", target, {"action": "navigate", "url": url, "goal": f"go to {target}"}, 0.85, raw)
            return

        # ── Nothing matched - offer to learn ──
        yield IntentResult("unknown", "unknown", "", {"text": f"I don't recognize '{raw}'. Teach me!"}, 0.0, raw)
