"""
chat_executor.py — Handles conversational intents using the LLM.
"""

import os
import logging
import requests
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

class ChatExecutor:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3").strip()
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

    def execute(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Generate a conversational response."""
        user_text = intent.raw_text or intent.data.get("topic", "Hello")
        logger.info(f"Chatting: {user_text}")

        try:
            if self.provider == "ollama":
                resp = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json={
                        "model": self.ollama_model,
                        "messages": [
                            {"role": "system", "content": "You are JARVIS, a helpful and witty AI assistant. Keep responses very concise and friendly."},
                            {"role": "user", "content": user_text}
                        ],
                        "stream": False
                    },
                    timeout=15
                )
                resp.raise_for_status()
                answer = resp.json().get("message", {}).get("content", "").strip()
            else:
                resp = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"},
                    json={
                        "model": self.openai_model,
                        "messages": [
                            {"role": "system", "content": "You are JARVIS, a helpful and witty AI assistant. Keep responses very concise and friendly."},
                            {"role": "user", "content": user_text}
                        ]
                    },
                    timeout=15
                )
                resp.raise_for_status()
                answer = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()

            return True, answer

        except Exception as e:
            logger.error(f"Chat error: {e}")
            return False, "I'm having trouble thinking right now."
