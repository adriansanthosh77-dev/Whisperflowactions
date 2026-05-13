"""
teach_mode.py — JARVIS Learning Engine

Two learning paths:
1. MANUAL: User demonstrates actions -> JARVIS records -> saves as workflow
2. AUTO-LLM: LLM solves an ACTION task once -> JARVIS caches it -> instant next time

IMPORTANT: Only repeatable ACTIONS (open, click, navigate, type) get cached.
Coding, creative, and analysis tasks ALWAYS go fresh to the LLM.
"""

import json
import os
import time
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

WORKFLOWS_PATH = os.path.join("data", "learned_workflows.json")


class TeachMode:
    """JARVIS Learning Engine — Record, Learn, Remember."""

    def __init__(self):
        self.recording = False
        self.recorded_steps = []
        self.workflows = self._load_workflows()
        logger.info(f"TeachMode initialized. {len(self.workflows)} learned workflows loaded.")

    # ── Persistence ───────────────────────────────────────────────────────

    def _load_workflows(self) -> dict:
        """Load all learned workflows from disk."""
        if os.path.exists(WORKFLOWS_PATH):
            try:
                with open(WORKFLOWS_PATH, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_workflows(self):
        """Persist all workflows to disk."""
        os.makedirs(os.path.dirname(WORKFLOWS_PATH), exist_ok=True)
        with open(WORKFLOWS_PATH, 'w') as f:
            json.dump(self.workflows, f, indent=2)

    # ── Manual Teaching (Record & Replay) ─────────────────────────────────

    def start_recording(self) -> str:
        """Start recording user actions for manual teaching."""
        self.recording = True
        self.recorded_steps = []
        logger.info("TeachMode: Recording started.")
        return "Recording started. Do what you want me to learn. Say 'stop recording' when done."

    def record_step(self, intent: str, app: str, data: dict):
        """Record a single action during manual teaching."""
        if not self.recording:
            return
        step = {
            "intent": intent,
            "app": app,
            "data": data,
            "timestamp": time.time()
        }
        self.recorded_steps.append(step)
        logger.info(f"TeachMode: Recorded step #{len(self.recorded_steps)}: {intent} -> {app}")

    def stop_recording(self) -> dict:
        """Stop recording and return the captured steps."""
        self.recording = False
        steps = self.recorded_steps.copy()
        self.recorded_steps = []
        logger.info(f"TeachMode: Recording stopped. {len(steps)} steps captured.")
        return {
            "steps": steps,
            "count": len(steps)
        }

    def save_manual_workflow(self, trigger: str, steps: list) -> str:
        """Save a manually recorded workflow with a trigger phrase."""
        trigger = trigger.lower().strip()
        self.workflows[trigger] = {
            "type": "manual",
            "steps": steps,
            "source": "user_demonstration",
            "created": datetime.now().isoformat(),
            "use_count": 0
        }
        self._save_workflows()
        logger.info(f"TeachMode: Saved manual workflow '{trigger}' ({len(steps)} steps)")
        return f"Got it! I'll remember '{trigger}' as a {len(steps)}-step workflow."

    # ── Auto-LLM Teaching (Learn Once, Execute Forever) ───────────────────

    def save_llm_workflow(self, trigger: str, steps: list, original_command: str) -> str:
        """Save an LLM-generated workflow so it never needs the LLM again."""
        trigger = trigger.lower().strip()
        self.workflows[trigger] = {
            "type": "auto_llm",
            "steps": steps,
            "original_command": original_command,
            "source": "llm_learned",
            "created": datetime.now().isoformat(),
            "use_count": 0
        }
        self._save_workflows()
        logger.info(f"TeachMode: Saved LLM workflow '{trigger}' ({len(steps)} steps)")
        return f"Learned! Next time you say '{trigger}', I'll do it instantly without the AI."

    # Intents that are safe to cache (repeatable actions)
    CACHEABLE_INTENTS = {
        "pc_action", "browser_action", "open_app", "launch_app",
        "send_message", "describe_screen",
    }

    # Intents that should NEVER be cached (need fresh LLM every time)
    NEVER_CACHE_INTENTS = {
        "code", "write_code", "create_task", "summarize", "analyze",
        "explain", "generate", "compose", "draft", "create",
    }

    def save_llm_result(self, original_command: str, steps: list):
        """Auto-save an LLM result, but ONLY if it's an action workflow.
        
        Coding, creative, and analysis tasks always go to the LLM fresh
        because their output changes every time. Only repeatable actions
        (open, click, navigate, type) get cached.
        """
        trigger = original_command.lower().strip()
        if trigger in self.workflows:
            return  # Already learned

        # Check if ALL steps are cacheable actions
        for step in steps:
            intent = step.get("intent", "")
            # If any step is a coding/creative task, don't cache
            if intent in self.NEVER_CACHE_INTENTS:
                logger.info(f"TeachMode: Skipping cache for '{trigger}' (contains '{intent}' - needs fresh LLM)")
                return
            # If the step data contains code-like content, don't cache
            data = step.get("data", {})
            if any(k in data for k in ("code", "script", "program", "function")):
                logger.info(f"TeachMode: Skipping cache for '{trigger}' (contains code content)")
                return

        # Only cache if we have at least one cacheable action
        has_action = any(step.get("intent", "") in self.CACHEABLE_INTENTS for step in steps)
        if not has_action:
            logger.info(f"TeachMode: Skipping cache for '{trigger}' (no cacheable actions)")
            return

        self.workflows[trigger] = {
            "type": "auto_cached",
            "steps": steps,
            "original_command": original_command,
            "source": "llm_auto_cache",
            "created": datetime.now().isoformat(),
            "use_count": 0
        }
        self._save_workflows()
        logger.info(f"TeachMode: Auto-cached action workflow for '{trigger}'")

    # ── Workflow Lookup ───────────────────────────────────────────────────

    def find_workflow(self, command: str) -> Optional[dict]:
        """Check if we have a learned workflow for this command."""
        t = command.lower().strip()
        
        # Exact match
        if t in self.workflows:
            self.workflows[t]["use_count"] = self.workflows[t].get("use_count", 0) + 1
            self._save_workflows()
            return self.workflows[t]

        # Fuzzy match against workflow triggers
        import difflib
        keys = list(self.workflows.keys())
        matches = difflib.get_close_matches(t, keys, n=1, cutoff=0.80)
        if matches:
            matched = matches[0]
            logger.info(f"TeachMode: Fuzzy matched workflow '{t}' -> '{matched}'")
            self.workflows[matched]["use_count"] = self.workflows[matched].get("use_count", 0) + 1
            self._save_workflows()
            return self.workflows[matched]

        return None

    # ── Status & Info ─────────────────────────────────────────────────────

    def list_workflows(self) -> list:
        """List all learned workflows with their stats."""
        result = []
        for trigger, data in self.workflows.items():
            result.append({
                "trigger": trigger,
                "type": data.get("type", "unknown"),
                "steps": len(data.get("steps", [])),
                "uses": data.get("use_count", 0),
                "source": data.get("source", "unknown")
            })
        return result

    def is_recording(self) -> bool:
        return self.recording

    def get_stats(self) -> dict:
        """Get learning statistics."""
        manual = sum(1 for w in self.workflows.values() if w.get("type") == "manual")
        auto = sum(1 for w in self.workflows.values() if w.get("type") in ("auto_llm", "auto_cached"))
        total_uses = sum(w.get("use_count", 0) for w in self.workflows.values())
        return {
            "total_workflows": len(self.workflows),
            "manual_taught": manual,
            "llm_learned": auto,
            "total_executions_saved": total_uses,
            "recording": self.recording
        }


# Singleton
_teach_mode = None

def get_teach_mode() -> TeachMode:
    global _teach_mode
    if _teach_mode is None:
        _teach_mode = TeachMode()
    return _teach_mode
