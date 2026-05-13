"""
intent_schema.py — Standard Python dataclasses for intent and context.
Removed Pydantic to ensure compatibility with Python 3.14.
"""
from typing import Optional, Any, Literal
from dataclasses import dataclass, field


@dataclass
class IntentResult:
    intent: str
    app: str = "browser"      # free-form: whatsapp | gmail | youtube | any site
    target: str = ""          # contact name, page title, task title, app name
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0   # 0.0–1.0, set by parser/planner
    raw_text: str = ""        # original transcription


SafetyLevel = Literal["safe", "confirm", "blocked", "forbidden"]


@dataclass
class ActionRequest:
    action_type: str           # browser | pc | message | file | system
    operation: str             # open | search | click | type | launch_app | etc.
    target: str = ""
    text: str = ""
    app: str = ""
    url: str = ""
    safety_level: SafetyLevel = "safe"
    requires_confirmation: bool = False
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    success: bool
    message: str = ""
    needs_user: bool = False
    blocked_reason: str = ""
    observed_state: dict[str, Any] = field(default_factory=dict)

    def as_tuple(self) -> tuple[bool, str]:
        if self.needs_user and self.blocked_reason:
            return False, self.blocked_reason
        return self.success, self.message


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
