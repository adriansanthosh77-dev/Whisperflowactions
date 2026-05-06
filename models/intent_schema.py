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

VALID_APPS = Literal["whatsapp", "gmail", "notion", "browser", "unknown"]


class IntentResult(BaseModel):
    intent: VALID_INTENTS
    app: VALID_APPS
    target: str = ""          # contact name, page title, task title, app name
    data: dict[str, Any] = Field(default_factory=dict) # message body, summary, etc.
    confidence: float = 1.0   # 0.0–1.0, set by parser
    raw_text: str = ""        # original transcription


class Context(BaseModel):
    active_app: str = ""
    url: str = ""
    selected_text: str = ""
    clipboard: str = ""
    dom: dict[str, Any] = Field(default_factory=dict)
    mouse: dict[str, Any] = Field(default_factory=dict)
    learning_hints: list[str] = Field(default_factory=list)
