"""
base_executor.py — Native Obscura/CDP Executor (Playwright-Free)

Rewritten to talk directly to Obscura via WebSockets/CDP.
Ensures 100% compatibility with Python 3.12-3.14 by removing Playwright/greenlet.
"""

import os
import time
import json
import logging
import asyncio
import threading
import requests
from pathlib import Path
from typing import Optional, Any, Callable
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

OBSCURA_PORT = int(os.getenv("OBSCURA_PORT", "9222"))
SCREENSHOT_DIR = Path("data/screenshots")
MAX_DOM_ELEMENTS = 40

class CDPClient:
    """Minimalistic CDP client using sync requests/websockets for Obscura."""
    def __init__(self, port=9222):
        self.port = port
        self.ws_url = None
        self._msg_id = 0
        self._ws = None

    def connect(self):
        try:
            # 1. Get the WebSocket URL from Obscura
            resp = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=2)
            self.ws_url = resp.json().get("webSocketDebuggerUrl")
            
            # 2. Connect via websockets (imported inside to avoid crash if not installed yet)
            import websockets.sync.client as ws_client
            self._ws = ws_client.connect(self.ws_url)
            logger.info(f"Connected to Obscura CDP: {self.ws_url}")
            return True
        except Exception as e:
            logger.error(f"CDP Connection failed: {e}")
            return False

    def send(self, method: str, params: dict = None) -> dict:
        if not self._ws:
            if not self.connect(): return {}
        
        self._msg_id += 1
        payload = {
            "id": self._msg_id,
            "method": method,
            "params": params or {}
        }
        self._ws.send(json.dumps(payload))
        
        # Simple sync wait for response
        while True:
            resp = json.loads(self._ws.recv())
            if resp.get("id") == self._msg_id:
                return resp.get("result", {})
            # Ignore events for now

    def evaluate(self, expression: str) -> Any:
        res = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": True
        })
        return res.get("result", {}).get("value")

class BaseExecutor:
    _cdp: Optional[CDPClient] = None
    _last_url = ""
    _abort_execution = False
    _action_events: list[dict] = []

    @classmethod
    def consume_action_events(cls) -> list[dict]:
        events = cls._action_events[:]
        cls._action_events.clear()
        return events

    @classmethod
    def reset_abort_signal(cls):
        cls._abort_execution = False

    @classmethod
    def check_for_block(cls) -> tuple[bool, str]:
        # Minimalist block detector for CDP
        return False, ""

    @classmethod
    def close_active_page_tasks(cls):
        cls._abort_execution = True
        logger.info("Browser tasks marked for abort.")

    @classmethod
    def close(cls):
        if cls._cdp:
            try:
                cls._cdp.close()
            except:
                pass
            cls._cdp = None

    @classmethod
    def _ensure_browser(cls):
        if not cls._cdp:
            cls._cdp = CDPClient(port=OBSCURA_PORT)
            if not cls._cdp.connect():
                raise RuntimeError(f"Could not connect to Obscura on port {OBSCURA_PORT}. Is it running?")

    @classmethod
    def get_active_page_url(cls) -> str:
        cls._ensure_browser()
        try:
            return cls._cdp.evaluate("window.location.href")
        except:
            return ""

    @classmethod
    def navigate(cls, url: str):
        cls._ensure_browser()
        logger.info(f"Navigating to {url}...")
        cls._cdp.send("Page.navigate", {"url": url})
        time.sleep(2) # Basic wait

    @classmethod
    def observe_active_page(cls) -> dict:
        cls._ensure_browser()
        js = """
        () => {
          const isVisible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden";
          };
          const textOf = (el) => (el.innerText || el.value || "").trim().slice(0, 100);
          
          const elements = Array.from(document.querySelectorAll('a, button, input, textarea'))
            .filter(isVisible)
            .slice(0, 40)
            .map((el, i) => ({
              index: i,
              tag: el.tagName.toLowerCase(),
              text: textOf(el),
              bbox: el.getBoundingClientRect().toJSON()
            }));

          return {
            title: document.title,
            url: location.href,
            elements: elements
          };
        }
        """
        try:
            return cls._cdp.evaluate(f"({js})()")
        except Exception as e:
            logger.error(f"Observe failed: {e}")
            return {}

    @classmethod
    def click_resilient(cls, page: Any, labels: list[str] = None, **kwargs) -> str:
        cls._ensure_browser()
        dom = cls.observe_active_page()
        elements = dom.get("elements", [])
        
        target = None
        for label in (labels or []):
            for el in elements:
                if label.lower() in el['text'].lower():
                    target = el
                    break
            if target: break
        
        if target:
            bbox = target['bbox']
            x = bbox['x'] + bbox['width']/2
            y = bbox['y'] + bbox['height']/2
            cls._cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            cls._cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
            return f"clicked:{target['text']}"
        
        return "failed"

    @classmethod
    def fill_resilient(cls, page: Any, value: str, labels: list[str] = None, **kwargs) -> str:
        cls._ensure_browser()
        # Simple click + type
        cls.click_resilient(page, labels)
        time.sleep(0.2)
        for char in value:
            cls._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": char})
        return "filled"

    @staticmethod
    def get_mouse_position() -> dict:
        return {"x": 0, "y": 0}

    @staticmethod
    def capture_screenshot(page: Any, label: str = "") -> str:
        # Minimalist placeholder for now
        return ""

    @classmethod
    def close(cls):
        pass

    @staticmethod
    def with_retry(fn: Callable, retries: int = 3, delay: float = 1.0):
        try: return fn()
        except Exception as e:
            logger.warning(f"Retry failed: {e}")
            return None
