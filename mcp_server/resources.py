"""
resources.py — MCP resources for JARVIS.

Exposes system context and status as read-only MCP resources
that LLMs can read to understand the current environment.
"""
import os
import json
import logging
import platform
from datetime import datetime

logger = logging.getLogger(__name__)


def register_resources(mcp):
    @mcp.resource("jarvis://context")
    def jarvis_context() -> str:
        """Current system context: active window, time, platform info.
        LLMs read this to understand what the user is currently doing.
        """
        try:
            import psutil
            import subprocess

            # Active window (Windows)
            active_window = "unknown"
            try:
                import pygetwindow as gw
                active = gw.getActiveWindow()
                if active:
                    active_window = active.title
            except Exception:
                pass

            # Battery
            battery_info = "N/A"
            try:
                batt = psutil.sensors_battery()
                if batt:
                    battery_info = f"{batt.percent}% {'plugged in' if batt.power_plugged else 'on battery'}"
            except Exception:
                pass

            now = datetime.now()
            return json.dumps({
                "platform": platform.system(),
                "time": now.strftime("%H:%M"),
                "date": now.strftime("%Y-%m-%d"),
                "active_window": active_window,
                "battery": battery_info,
            }, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("jarvis://status")
    def jarvis_status() -> str:
        """JARVIS system status: which subsystems are available and their state."""
        status = {
            "version": "1.0.0",
            "tts_provider": os.getenv("TTS_PROVIDER", "edge"),
            "llm_provider": os.getenv("LLM_PROVIDER", "ollama"),
            "vision": "directml" if os.getenv("USE_DIRECTML", "").lower() == "true" else "moondream",
            "setup_complete": os.getenv("JARVIS_SETUP_DONE", "false") == "true",
            "exa_configured": bool(os.getenv("EXA_API_KEY", "")),
            "composio_configured": bool(os.getenv("COMPOSIO_API_KEY", "")),
            "python": platform.python_version(),
        }
        return json.dumps(status, indent=2)

    @mcp.resource("jarvis://reflexes")
    def jarvis_reflexes() -> str:
        """List all available JARVIS reflexes (PC and browser automation commands)."""
        try:
            from core.planner import Planner
            p = Planner()
            reflexes = p.list_reflexes()
            return "\n".join(reflexes)
        except Exception as e:
            return f"Error listing reflexes: {e}"

    @mcp.resource("jarvis://config")
    def jarvis_config() -> str:
        """Current JARVIS configuration from .env (keys redacted)."""
        config = {}
        for key, val in sorted(os.environ.items()):
            if key.startswith(("JARVIS_", "TTS_", "LLM_", "STT_",
                                "CODING_", "CREATIVE_", "ANALYSIS_",
                                "RESEARCH_", "USE_", "OLLAMA_",
                                "MOONDREAM_", "EXA_", "COMPOSIO_")):
                if "KEY" in key or "SECRET" in key or "PASSWORD" in key:
                    val = "***REDACTED***"
                config[key] = val
        return json.dumps(config, indent=2)
