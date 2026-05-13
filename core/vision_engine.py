"""
vision_engine.py — Local Vision Engine with DirectML + Ollama fallback.

Priority:
  1. DirectML (ONNX Runtime, GPU-accelerated) — fastest on Windows with DirectX 12
  2. Ollama/Moondream — local VLM via Ollama API
"""

import os
import logging
import requests
import base64
from typing import Optional

logger = logging.getLogger(__name__)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
MOONDREAM_MODEL = os.getenv("MOONDREAM_MODEL", "moondream").strip()

class VisionEngine:
    def __init__(self):
        self._directml = None
        logger.info(f"Vision Engine initialized with model: {MOONDREAM_MODEL}")

    def _get_directml(self):
        if self._directml is None:
            try:
                from core.vision_directml import get_directml_vision
                self._directml = get_directml_vision()
                if self._directml.is_available():
                    logger.info("DirectML vision engine is available (GPU-accelerated)")
                else:
                    logger.info("DirectML vision engine not available, using Ollama/Moondream")
            except Exception as e:
                logger.debug(f"DirectML init skipped: {e}")
                self._directml = False
        return self._directml if self._directml else None

    def analyze_screenshot(self, screenshot_path: str, prompt: str) -> Optional[str]:
        """Analyzes a local screenshot. Tries DirectML first, falls back to Moondream."""
        if not os.path.exists(screenshot_path):
            logger.error(f"Screenshot not found at {screenshot_path}")
            return "I'm sorry, I couldn't find the screenshot to analyze."

        # Try DirectML first (faster, GPU-accelerated)
        dml = self._get_directml()
        if dml:
            try:
                result = dml.analyze_screenshot(screenshot_path, prompt)
                if result:
                    return result
            except Exception as e:
                logger.debug(f"DirectML vision failed, falling back: {e}")

        # Fallback to Ollama/Moondream
        return self._analyze_ollama(screenshot_path, prompt)

    def _analyze_ollama(self, screenshot_path: str, prompt: str) -> Optional[str]:
        try:
            with open(screenshot_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "model": MOONDREAM_MODEL,
                "prompt": prompt,
                "stream": False,
                "images": [img_b64],
                "keep_alive": "10m",
                "options": {"num_predict": 100, "temperature": 0.2, "num_ctx": 512}
            }

            logger.info(f"Analyzing screen with {MOONDREAM_MODEL}...")
            resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=45)
            resp.raise_for_status()

            description = resp.json().get("response", "").strip()
            logger.info(f"Vision analysis complete: {description[:50]}...")
            return description

        except Exception as e:
            logger.error(f"Vision error: {e}")
            return "I encountered an error while trying to look at your screen."

    def detect_objects(self, screenshot_path: str) -> list[dict]:
        """Detect objects on screen using DirectML YOLO (if available)."""
        dml = self._get_directml()
        if dml:
            try:
                return dml.detect_objects(screenshot_path)
            except Exception as e:
                logger.debug(f"DirectML object detection failed: {e}")
        return []

    def find_object(self, screenshot_path: str, target: str) -> Optional[dict]:
        """Find an object on screen by description using DirectML YOLO."""
        dml = self._get_directml()
        if dml:
            try:
                return dml.find_object(screenshot_path, target)
            except Exception as e:
                logger.debug(f"DirectML object find failed: {e}")
        return None


def get_vision_engine():
    return VisionEngine()
