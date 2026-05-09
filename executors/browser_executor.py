"""
browser_executor.py — Browser actions using native CDP (Playwright-Free).
"""

import os
import time
import logging
import json
import requests
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

NOTION_NEW_PAGE_URL = "https://www.notion.so/new"

class BrowserExecutor(BaseExecutor):

    def open_url(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        url = intent.data.get("url", "")
        if not url:
            return False, "No URL to open."

        try:
            self.navigate(url)
            return True, f"Opened {url}"
        except Exception as e:
            return False, f"Failed to open {url}: {str(e)[:60]}"

    def summarize_page(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Get page text and summarize with GPT."""
        try:
            self._ensure_browser()
            # Get text via CDP
            page_text = self._cdp.evaluate("document.body.innerText")[:6000]
            style = intent.data.get("style", "bullet")
            summary = self._gpt_summarize(page_text, style)
            return True, f"Page Summary:\n{summary}"
        except Exception as e:
            return False, f"Summarize failed: {str(e)[:80]}"

    def _gpt_summarize(self, text: str, style: str = "bullet") -> str:
        format_instruction = (
            "in 4-6 concise bullet points" if style == "bullet"
            else "in 2-3 short paragraphs"
        )
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": f"Summarize the following web page content {format_instruction}. Focus on key information, skip navigation/ads."},
                {"role": "user", "content": text},
            ],
            "max_tokens": 350,
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def adaptive_browser_task(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Simple adaptive task for CDP."""
        goal = intent.data.get("goal") or intent.raw_text or "complete browser task"
        logger.info(f"Adaptive task started: {goal}")
        
        # In this minimal CDP version, we just do one click/type attempt
        # Real adaptive logic would be more complex
        self.click_resilient(None, labels=intent.data.get("labels", []))
        if intent.data.get("text"):
            self.fill_resilient(None, intent.data.get("text"), labels=intent.data.get("labels", []))
            
        return True, f"Attempted action for: {goal}"
