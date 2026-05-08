"""
block_detector.py — Detects CAPTCHAs, bot checks, and login walls.

Uses DOM text patterns and optional screenshot analysis to determine
if the automation is blocked and needs human intervention.
"""

import os
import logging
import json
import base64
from typing import Optional
from openai import OpenAI
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
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None

    def is_blocked(self, dom: dict, screenshot_path: Optional[str] = None) -> tuple[bool, str]:
        """
        Returns (is_blocked, reason).
        """
        # 1. Quick DOM text check
        page_text = f"{dom.get('title', '')} {json.dumps(dom.get('appStructure', {}))}".lower()
        for kw in BLOCK_KEYWORDS:
            if kw in page_text:
                return True, f"Detected: {kw}"

        # 2. Vision check (if screenshot provided and API key available)
        if screenshot_path and self.client:
            try:
                with open(screenshot_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')

                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
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
                    max_tokens=100,
                    response_format={"type": "json_object"}
                )
                result = json.loads(response.choices[0].message.content)
                if result.get("blocked"):
                    return True, result.get("reason", "Visual block detected")
            except Exception as e:
                logger.warning(f"Vision block detection failed: {e}")

        return False, ""
