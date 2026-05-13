"""
intent_sequencer.py — Sequential thinking intent classifier.

Classifies user commands into execution tiers and routes them appropriately:
  - REFLEX: instant dictionary/regex match (<10ms)
  - PAID: needs API key (optional)
  - RESEARCH: needs web search (Exa/browser)
  - CODING: needs filesystem operations
  - APP: needs external app integration (Composio)
  - COMPLEX: needs MCP agent orchestration
"""
import os
import re
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class IntentSequencer:
    """Sequential thinking intent parser for JARVIS commands."""

    # Keywords that signal each category
    PAID_KEYWORDS = [
        "dall-e", "midjourney", "gpt-4", "claude-sonnet", "claude-opus",
        "elevenlabs", "stable diffusion", "runway", "sora",
    ]

    RESEARCH_KEYWORDS = [
        "research", "find out", "what is", "who is", "how does",
        "search for", "look up", "google", "wikipedia",
        "latest news", "current events", "weather in",
        "define", "meaning of", "explain",
    ]

    CODING_KEYWORDS = [
        "write code", "create a function", "implement", "debug",
        "refactor", "fix bug", "write test", "add feature",
        "create file", "edit file", "read file",
        "python", "javascript", "typescript", "rust", "go ",
        "npm install", "pip install", "git commit",
    ]

    APP_KEYWORDS = [
        "send email", "create issue", "slack message",
        "notion", "jira", "asana", "linear",
        "google calendar", "google drive",
        "send message to ", "post on ",
    ]

    COMPLEX_MARKERS = [
        "first", "then", "after that", "finally",
        "step by step", "multi step", "automate",
        "create a workflow", "every day", "every week",
        "whenever", "monitor", "watch for",
    ]

    def __init__(self):
        pass

    def classify(self, command: str, context: Optional[dict] = None) -> dict:
        cmd_lower = command.lower().strip()
        sub_commands = self._split_commands(cmd_lower)

        # Check for compound commands first
        is_compound = len(sub_commands) > 1

        # Step 1: Check for paid API mentions
        for kw in self.PAID_KEYWORDS:
            if kw in cmd_lower:
                return {"tier": "PAID", "confidence": 0.9, "reasoning": f"Paid service: {kw}", "sub_commands": sub_commands}

        # Step 2: Check for complex multi-step
        complex_score = sum(1 for kw in self.COMPLEX_MARKERS if kw in cmd_lower)
        if complex_score >= 1 or is_compound:
            return {"tier": "COMPLEX", "confidence": min(0.6 + complex_score * 0.1, 0.95), "reasoning": f"Multi-step ({len(sub_commands)} parts)", "sub_commands": sub_commands}

        # Step 3: Check for research needs
        research_score = sum(1 for kw in self.RESEARCH_KEYWORDS if kw in cmd_lower)
        if research_score >= 1:
            return {"tier": "RESEARCH", "confidence": min(0.5 + research_score * 0.1, 0.95), "reasoning": f"Research keywords ({research_score})", "sub_commands": sub_commands}

        # Step 4: Check for coding needs
        coding_score = sum(1 for kw in self.CODING_KEYWORDS if kw in cmd_lower)
        if coding_score >= 1:
            return {"tier": "CODING", "confidence": min(0.5 + coding_score * 0.1, 0.95), "reasoning": f"Coding keywords ({coding_score})", "sub_commands": sub_commands}

        # Step 5: Check for app integration
        app_score = sum(1 for kw in self.APP_KEYWORDS if kw in cmd_lower)
        if app_score >= 1:
            return {"tier": "APP", "confidence": min(0.5 + app_score * 0.1, 0.95), "reasoning": f"App keywords ({app_score})", "sub_commands": sub_commands}

        # Step 6: Check for known reflex (strict — exact match or high fuzzy only)
        reflex_check = self._check_reflex_strict(cmd_lower)
        if reflex_check["is_reflex"]:
            return {"tier": "REFLEX", "confidence": reflex_check["confidence"], "reasoning": f"Known reflex: {reflex_check['operation']}", "sub_commands": sub_commands, "reflex": reflex_check}

        # Default: unknown command
        return {"tier": "UNKNOWN", "confidence": 0.0, "reasoning": "No category matched", "sub_commands": sub_commands}

    def _check_reflex_strict(self, cmd: str) -> dict:
        """Check for known reflex with high confidence."""
        try:
            from core.planner import Planner
            p = Planner()
            if p.can_fast_plan(cmd):
                return {"is_reflex": True, "operation": "fast_plan_match", "confidence": 0.96}
        except Exception:
            pass

        return {"is_reflex": False, "operation": None, "confidence": 0.0}

    def _check_reflex(self, cmd: str) -> dict:
        """Check if a command matches a known reflex (fast path)."""
        try:
            from core.planner import Planner
            p = Planner()
            can_fast = p.can_fast_plan(cmd)
            if can_fast:
                return {"is_reflex": True, "operation": can_fast, "confidence": 0.96}
        except Exception:
            pass

        # Fallback: check against known reflex keys
        try:
            from core.planner import pc_reflexes
            if cmd in pc_reflexes:
                op, extra = pc_reflexes[cmd]
                return {"is_reflex": True, "operation": op, "extra": extra, "confidence": 0.96}

            # Fuzzy match
            from rapidfuzz import process, fuzz
            match = process.extractOne(cmd, list(pc_reflexes.keys()), scorer=fuzz.ratio, score_cutoff=75)
            if match:
                op, extra = pc_reflexes[match[0]]
                return {"is_reflex": True, "operation": op, "extra": extra, "confidence": 0.85}
        except Exception:
            pass

        return {"is_reflex": False, "operation": None, "confidence": 0.0}

    def _split_commands(self, cmd: str) -> list:
        """Split compound commands into individual sub-commands."""
        parts = re.split(r'\s+(and|then|after that|finally|,)\s+', cmd)
        # Filter out the separators and clean up
        return [p.strip() for p in parts if p.strip() and p.strip() not in ['and', 'then', 'after that', 'finally', ',']]

    def route(self, command: str, context: Optional[dict] = None) -> str:
        """
        Route a command to the appropriate handler based on classification.
        Returns the result string.
        """
        classification = self.classify(command, context)
        tier = classification["tier"]
        confidence = classification["confidence"]

        logger.info(f"IntentSequencer: {tier} ({confidence:.2f}) <- {command[:60]}")

        if tier == "REFLEX":
            return self._execute_reflex(command)

        if tier == "RESEARCH":
            return self._route_research(command)

        if tier == "CODING":
            return self._route_coding(command)

        if tier == "COMPLEX":
            return self._route_complex(command)

        if tier == "PAID":
            return self._route_paid(command)

        if tier == "APP":
            return self._route_app(command)

        # Unknown: fall through to LLM
        return self._route_llm(command)

    def _execute_reflex(self, command: str) -> str:
        """Execute a reflex directly through the existing PCExecutor/BrowserExecutor."""
        try:
            from core.planner import Planner
            from core.action_router import ActionRouter

            p = Planner()
            router = ActionRouter()
            results = []
            for intent in p.plan(command, {}):
                success, msg = router.route(intent, {})
                results.append(f"[{'OK' if success else 'FAIL'}] {msg}")
            return "\n".join(results) if results else "No reflex executed."
        except Exception as e:
            return f"Reflex execution failed: {e}"

    def _route_research(self, command: str) -> str:
        """Route to research: Exa search or browser search."""
        if os.getenv("EXA_API_KEY", ""):
            return "[MCP Agent] Exa research available. Would trigger MCP agent with exa_search tool."
        return "[MCP Agent] Research via browser search. Would trigger browser_search tool."

    def _route_coding(self, command: str) -> str:
        return "[MCP Agent] Coding task. Would use fs_read/fs_write/fs_edit tools via MCP agent."

    def _route_complex(self, command: str) -> str:
        return "[MCP Agent] Complex multi-step task. Would use MCP agent with sequential tool orchestration."

    def _route_paid(self, command: str) -> str:
        return "[MCP Agent] Paid API task. Would route to configured paid provider (if API key set)."

    def _route_app(self, command: str) -> str:
        return "[MCP Agent] External app integration. Would use Composio tools via MCP agent."

    def _route_llm(self, command: str) -> str:
        """Fallback: route to LLM."""
        return "[LLM Fallback] Would call Ollama/browser LLM for this command."
