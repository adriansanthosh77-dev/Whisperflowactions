"""
block_detector.py — Detects CAPTCHAs, bot checks, and login walls.
Removed OpenAI SDK for Python 3.14 compatibility.
"""

import os
import logging
import json
import base64
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BLOCK_KEYWORDS = [
    "captcha", "robot check", "verify you are human", "not a robot",
    "access denied", "please log in", "sign in to continue", "security check",
    "press and hold", "solve the puzzle"
]

class BlockDetector:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")

    def is_blocked(self, dom: dict, screenshot_path: Optional[str] = None) -> tuple[bool, str]:
        # 1. Quick DOM text check
        page_text = f"{dom.get('title', '')} {json.dumps(dom.get('appStructure', {}))}".lower()
        for kw in BLOCK_KEYWORDS:
            if kw in page_text:
                return True, f"Detected: {kw}"

        # 2. Vision check (if screenshot provided and API key available)
        if screenshot_path and self.api_key:
            try:
                with open(screenshot_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

                url = "https://api.openai.com/v1/chat/completions"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                payload = {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Is this page showing a CAPTCHA, robot check, or login wall that prevents automation? Answer with a JSON object: {\"blocked\": true/false, \"reason\": \"...\"}"},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                                },
                            ],
                        }
                    ],
                    "max_tokens": 100,
                    "response_format": {"type": "json_object"}
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=20)
                resp.raise_for_status()
                result = json.loads(resp.json()["choices"][0]["message"]["content"])
                if result.get("blocked"):
                    return True, result.get("reason", "Visual block detected")
            except Exception as e:
                logger.warning(f"Vision block detection failed: {e}")

        return False, ""
