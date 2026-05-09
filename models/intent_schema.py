"""
intent_schema.py — Standard Python dataclasses for intent and context.
Removed Pydantic to ensure compatibility with Python 3.14.
"""
from typing import Optional, Any
from dataclasses import dataclass, field


@dataclass
class IntentResult:
    intent: str
    app: str = "browser"      # free-form: whatsapp | gmail | youtube | any site
    target: str = ""          # contact name, page title, task title, app name
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0   # 0.0–1.0, set by parser/planner
    raw_text: str = ""        # original transcription


@dataclass
class Context:
    active_app: str = ""
    url: str = ""
    selected_text: str = ""
    clipboard: str = ""
    dom: dict[str, Any] = field(default_factory=dict)
    mouse: dict[str, Any] = field(default_factory=dict)
    learning_hints: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list) # [{command, success, result}]
