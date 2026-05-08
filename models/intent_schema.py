"""
intent_schema.py — Pydantic models for intent and context.

app is now a free-form str so the planner can return any app/website name
(youtube, twitter, linear, bank, etc.) without hitting a validation error.
The router handles URL resolution for unknown apps.
"""
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field


VALID_INTENTS = Literal[
    "send_message",
    "summarize",
    "reply_professionally",
    "create_task",
    "open_app",
    "browser_action",
    "unknown",
]


class IntentResult(BaseModel):
    intent: VALID_INTENTS
    app: str = "browser"      # free-form: whatsapp | gmail | youtube | any site
    target: str = ""          # contact name, page title, task title, app name
    data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0   # 0.0–1.0, set by parser/planner
    raw_text: str = ""        # original transcription


class Context(BaseModel):
    active_app: str = ""
    url: str = ""
    selected_text: str = ""
    clipboard: str = ""
    dom: dict[str, Any] = Field(default_factory=dict)
    mouse: dict[str, Any] = Field(default_factory=dict)
    learning_hints: list[str] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list) # [{command, success, result}]
