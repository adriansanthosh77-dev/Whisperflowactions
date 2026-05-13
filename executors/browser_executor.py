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
_OLLAMA_MODEL_CACHE = None


def _resolve_ollama_model() -> str:
    global _OLLAMA_MODEL_CACHE
    if _OLLAMA_MODEL_CACHE:
        return _OLLAMA_MODEL_CACHE
    configured = os.getenv("OLLAMA_MODEL", "llama3.2-vision")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=1.5)
        resp.raise_for_status()
        models = [m.get("name", "") for m in resp.json().get("models", [])]
        if configured in models or f"{configured}:latest" in models:
            _OLLAMA_MODEL_CACHE = configured
        elif models:
            _OLLAMA_MODEL_CACHE = models[0]
        else:
            _OLLAMA_MODEL_CACHE = configured
    except Exception:
        _OLLAMA_MODEL_CACHE = configured
    return _OLLAMA_MODEL_CACHE

class BrowserExecutor(BaseExecutor):

    def _click_ordinal(self, target: str, ordinal: str) -> tuple[bool, str]:
        """Find the Nth element matching the target keyword and click it."""
        mapping = {"first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4, "last": -1}
        idx = mapping.get(ordinal, 0)
        
        target_json = json.dumps(target.lower())
        js = f"""
        (() => {{
            let items;
            const target_l = {target_json};
            if (target_l === "video") {{
                items = Array.from(document.querySelectorAll('ytd-video-renderer, ytd-grid-video-renderer, ytd-rich-item-renderer, a[href*="/watch?v="]'));
                items = items.filter(el => el.getBoundingClientRect().width > 20);
                const renderers = new Set();
                const uniqueItems = [];
                for (const el of items) {{
                    const renderer = el.closest('ytd-video-renderer, ytd-grid-video-renderer, ytd-rich-item-renderer');
                    if (renderer) {{
                        if (!renderers.has(renderer)) {{
                            renderers.add(renderer);
                            uniqueItems.push(renderer);
                        }}
                    }} else {{
                        uniqueItems.push(el);
                    }}
                }}
                items = uniqueItems;
            }} else {{
                items = Array.from(document.querySelectorAll('a, button, [role="button"], [role="link"], input'));
            }}
            
            const elements = items.map(el => ({{
                el: el,
                text: (el.innerText || el.getAttribute('aria-label') || el.title || el.placeholder || "").toLowerCase(),
                role: el.getAttribute('role') || el.tagName.toLowerCase(),
                href: el.href || (el.querySelector ? (el.querySelector('a')?.href || "") : ""),
                className: el.className || "",
                rect: el.getBoundingClientRect()
            }})).filter(i => i.rect.width > 5 && i.rect.height > 5);
            
            const matches = [];
            for (const item of elements) {{
                let is_match = false;
                if (target_l === "video") is_match = true;
                else if (item.text.includes(target_l)) is_match = true;
                else if (target_l === "link" && item.href) is_match = true;
                else if (target_l === "button" && (item.role === "button" || item.className.toLowerCase().includes("btn"))) is_match = true;
                
                if (is_match) matches.push(item);
            }}
            
            if (matches.length === 0) return {{error: "No matches found"}};
            
            matches.sort((a, b) => {{
                if (Math.abs(a.rect.top - b.rect.top) < 20) return a.rect.left - b.rect.left;
                return a.rect.top - b.rect.top;
            }});
            
            let i = {idx};
            if (i === -1) i = matches.length - 1;
            if (i >= matches.length) return {{error: `Only ${{matches.length}} matches found`}};
            
            const best = matches[i];
            best.el.scrollIntoView({{block: "center", inline: "center"}});
            const newRect = best.el.getBoundingClientRect();
            return {{
                x: newRect.left + newRect.width / 2,
                y: newRect.top + newRect.height / 2
            }};
        }})()
        """
        self._ensure_browser()
        result = self._cdp.evaluate(js)
        if not result:
            return False, "Failed to evaluate click script."
        if "error" in result:
            return False, result["error"]
            
        self.click_at(result["x"], result["y"])
        return True, f"Clicked the {ordinal} {target}."

    def check_for_blocking_elements(self) -> tuple[bool, str]:
        """Check the current DOM for common login, captcha, or bot-blocking indicators."""
        self._ensure_browser()
        js = """
        (() => {
            const text = document.body.innerText.toLowerCase();
            const markers = ["login", "sign in", "captcha", "verify you are human", "verify your identity", "access denied", "robot", "cloudflare"];
            for (let m of markers) {
                if (text.includes(m)) return m;
            }
            return null;
        })()
        """
        try:
            found = self._cdp.evaluate(js)
            if found:
                return True, f"I've detected a possible blocking screen ('{found}'). Please handle the interaction, and I'll continue once you're ready."
        except:
            pass
        return False, ""

    def execute(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        goal = intent.data.get("goal") or intent.raw_text
        action = intent.data.get("action")
        ordinal = intent.data.get("ordinal")
        target = intent.data.get("target")

        if action in ("open", "navigate"):
            return self.open_url(intent, context)

        if action == "agent_loop":
            return self._browser_agent_loop(goal, max_steps=int(intent.data.get("max_steps", 10)))

        if action == "scroll":
            return self._scroll(intent.data.get("direction", "down"))
            
        if action == "search":
            query = intent.data.get("query") or intent.data.get("text")
            if query:
                search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"
                self.navigate(search_url, wait=True)
                return True, f"Searched for {query} directly."

        if ordinal and action == "click":
            return self._click_ordinal(target, ordinal)

        return self._browser_agent_loop(goal, max_steps=intent.data.get("max_steps", 10))

    def _scroll(self, direction: str) -> tuple[bool, str]:
        direction = (direction or "down").lower()
        pixels = -700 if direction in ("up", "back", "previous") else 700
        try:
            self._ensure_browser()
            self._cdp.evaluate(f"window.scrollBy({{top: {pixels}, left: 0, behavior: 'smooth'}})")
            return True, f"Scrolled {direction}."
        except Exception as e:
            return False, f"Scroll failed: {str(e)[:80]}"

    def run_taught_workflow(self, steps: list[dict]) -> tuple[bool, str]:
        if not steps:
            return False, "No taught workflow steps were saved."

        useful_steps = 0
        for index, step in enumerate(steps[:30], start=1):
            if self._abort_execution:
                return False, "Taught workflow was aborted."

            blocked, reason = self.check_for_block()
            if blocked:
                return False, f"Blocked during taught workflow: {reason}"

            step_type = step.get("type")
            try:
                if step_type == "navigate":
                    url = step.get("url", "")
                    if not url:
                        continue
                    self.navigate(url, wait=True)
                    useful_steps += 1
                elif step_type == "click":
                    result = self._run_selector_action("click", step.get("selector", ""))
                    if str(result).startswith("failed") and step.get("label"):
                        result = self._run_dom_action("click", labels=[step.get("label", "")])
                    if str(result).startswith("failed"):
                        return False, f"Taught click failed at step {index}: {step.get('label', step.get('selector', 'target'))}"
                    useful_steps += 1
                elif step_type == "fill":
                    result = self._run_selector_action("fill", step.get("selector", ""), step.get("value", ""))
                    if str(result).startswith("failed") and step.get("label"):
                        result = self._run_dom_action("fill", labels=[step.get("label", "")], value=step.get("value", ""))
                    if str(result).startswith("failed"):
                        return False, f"Taught fill failed at step {index}: {step.get('label', step.get('selector', 'field'))}"
                    useful_steps += 1
                elif step_type == "press":
                    self.press_key(step.get("key", "Enter"))
                    useful_steps += 1
                elif step_type == "needs_user":
                    return False, step.get("reason", "This workflow needs the user for a sensitive field.")
            except Exception as e:
                return False, f"Taught workflow failed at step {index}: {str(e)[:80]}"

            time.sleep(0.35)

        if useful_steps == 0:
            return False, "No replayable taught workflow steps were found."
        return True, f"Ran taught workflow with {useful_steps} steps."

    def open_url(self, intent: IntentResult, context: Context, wait: bool = False) -> tuple[bool, str]:
        url = intent.data.get("url") or intent.target or ""
        if not url:
            return False, "No URL to open."

        try:
            self.navigate(url, wait=wait)
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
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3.2:1b")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": f"Summarize the following web page content {format_instruction}. Focus on key information, skip navigation/ads."},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 500, "num_ctx": 4096},
        }
        try:
            resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.warning(f"_gpt_summarize via Ollama failed: {e}")
            return f"Summary unavailable. (Ollama unreachable: {str(e)[:60]})"

    def adaptive_browser_task(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Observe-act browser loop for generic tasks."""
        goal = intent.data.get("goal") or intent.raw_text or "complete browser task"
        logger.info(f"Adaptive task started: {goal}")

        action = intent.data.get("action", "auto")
        labels = intent.data.get("labels", [])
        text = intent.data.get("text", "")
        key = intent.data.get("key", "")

        if action in ("click", "auto") and labels:
            self.click_resilient(None, labels=labels)

        if action in ("type", "auto") and text:
            self.fill_resilient(None, text, labels=labels)

        if action == "press" and key:
            self.press_key(key)
            return True, f"Pressed {key}"
        elif key:
            time.sleep(0.2)
            self.press_key(key)
            return True, f"Typed and pressed {key}"

        if action in ("click", "type", "auto") and (labels or text):
            return True, f"Completed {action} for: {goal}"

        return self._browser_agent_loop(goal, max_steps=int(intent.data.get("max_steps", 5)))

    def _browser_agent_loop(self, goal: str, max_steps: int = 5) -> tuple[bool, str]:
        last_action = ""
        for i in range(max_steps):
            blocked, reason = self.check_for_block()
            if blocked:
                return False, f"Blocked: {reason}"

            dom = self.observe_active_page()
            decision = self._decide_next_action(goal, dom, last_action)
            action = decision.get("action", "done")
            logger.info("Browser loop step %s: %s", i + 1, decision)

            if action == "done":
                return True, decision.get("reason", "Task appears complete.")
            if action == "navigate":
                self.navigate(decision.get("url", ""))
            elif action == "click":
                result = self.click_resilient(None, labels=decision.get("labels", []))
                if str(result).startswith("failed"):
                    return False, f"Could not click target for: {goal}"
            elif action == "fill":
                result = self.fill_resilient(None, decision.get("text", ""), labels=decision.get("labels", []))
                if str(result).startswith("failed"):
                    return False, f"Could not type target for: {goal}"
            elif action == "press":
                self.press_key(decision.get("key", "Enter"))
            else:
                return False, f"Unknown browser action: {action}"

            last_action = json.dumps(decision)
            time.sleep(0.7)
            
            # --- LOOP BREAKER: If we just filled a field, always press Enter next ---
            if action == "fill":
                self.press_key("Enter")
                time.sleep(1.0)

        return True, f"Reached step limit after working on: {goal}"

    def _decide_next_action(self, goal: str, dom: dict, last_action: str) -> dict:
        local = self._local_decision(goal, dom)
        if local:
            return local
        return self._ollama_decision(goal, dom, last_action)

    def _local_decision(self, goal: str, dom: dict) -> dict | None:
        g = goal.lower()
        elements = dom.get("elements", [])
        body = (dom.get("bodyText") or "").lower()

        if any(word in body for word in ["sent", "saved", "created", "published"]):
            return {"action": "done", "reason": "Completion text is visible."}

        if "click" in g:
            target = g.split("click", 1)[-1].strip(" .")
            if target:
                return {"action": "click", "labels": [target]}

        if any(k in g for k in ["accept cookies", "accept all cookies", "allow"]):
            return {"action": "click", "labels": ["Accept all", "Accept", "Allow", "Continue"]}

        if "search" in g:
            query = g.split("search", 1)[-1].replace("for", "", 1).strip(" .")
            if query:
                return {"action": "fill", "labels": ["Search", "Search input"], "text": query}

        if any(el.get("tag") in ("input", "textarea") or el.get("role") in ("textbox", "searchbox") for el in elements):
            if any(k in g for k in ["type", "write", "enter"]):
                text = goal.split(" ", 1)[-1]
                return {"action": "fill", "labels": ["Message", "Search", "Text", "Input"], "text": text}

        return None

    def _ollama_decision(self, goal: str, dom: dict, last_action: str) -> dict:
        model = _resolve_ollama_model()
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        compact_dom = {
            "title": dom.get("title", ""),
            "url": dom.get("url", ""),
            "bodyText": (dom.get("bodyText") or "")[:1200],
            "elements": dom.get("elements", [])[:30],
        }
        prompt = (
            "You control a browser. Return JSON only. Choose exactly one action.\n"
            "Allowed actions:\n"
            '{"action":"click","labels":["visible text or aria label"]}\n'
            '{"action":"fill","labels":["field label"],"text":"text to type"}\n'
            '{"action":"press","key":"Enter"}\n'
            '{"action":"navigate","url":"https://..."}\n'
            '{"action":"done","reason":"why"}\n'
            f"Goal: {goal}\nLast action: {last_action or 'none'}\nPage: {json.dumps(compact_dom)}"
        )
        try:
            resp = requests.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "num_predict": 120, "num_ctx": 2048},
                },
                timeout=18,
            )
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "{}")
            return json.loads(content)
        except Exception as e:
            logger.warning("Ollama browser decision failed: %s", e)
            return {"action": "done", "reason": "No reliable next action found."}
