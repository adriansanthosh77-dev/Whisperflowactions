"""
agent_manager.py — Manage custom JARVIS personalities.

Allows saving/loading named agents with custom:
- System Prompts
- Models (e.g. gpt-4o vs local llama)
- Isolated Feedback/Learning (optional)
"""

import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

AGENTS_DIR = Path("data/agents")

class AgentConfig:
    def __init__(self, name: str, system_prompt: str = "", model: str = "", provider: str = ""):
        self.name = name
        self.system_prompt = system_prompt
        self.model = model
        self.provider = provider

class AgentManager:
    def __init__(self):
        AGENTS_DIR.mkdir(parents=True, exist_ok=True)

    def save_agent(self, name: str, system_prompt: str, model: str = "", provider: str = ""):
        """Save a new agent personality."""
        config = {
            "name": name,
            "system_prompt": system_prompt,
            "model": model,
            "provider": provider
        }
        path = AGENTS_DIR / f"{name.lower().replace(' ', '_')}.json"
        with open(path, "w") as f:
            json.dump(config, f, indent=2)
        logger.info(f"Agent '{name}' saved to {path}")
        return path

    def load_agent(self, name_or_path: str) -> dict:
        """Load an agent personality."""
        name = name_or_path.lower().replace(' ', '_')
        path = AGENTS_DIR / f"{name}.json"
        if not path.exists():
            # Try direct path
            path = Path(name_or_path)
            if not path.exists():
                return {}
        
        with open(path, "r") as f:
            return json.load(f)

    def list_agents(self) -> list[str]:
        return [f.stem for f in AGENTS_DIR.glob("*.json")]

def get_agent_manager():
    return AgentManager()
