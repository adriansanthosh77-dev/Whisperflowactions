"""
browser_executor.py — Generic browser actions (open URL, summarize page, Notion task).
"""

import os
import time
import logging
import json
from openai import OpenAI
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)
client = None


def get_openai_client() -> OpenAI:
    global client
    if client is None:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return client


def has_valid_openai_key() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "sk-..." and not key.endswith("..."))

NOTION_NEW_PAGE_URL = "https://www.notion.so/new"

# Notion selectors (Web app)
SEL_NOTION_TITLE = 'div[placeholder="Untitled"]'
SEL_NOTION_BODY  = 'div[contenteditable="true"].notranslate'


class BrowserExecutor(BaseExecutor):

    def open_url(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        url = intent.data.get("url", "")
        if not url:
            return False, "No URL to open."

        def _execute():
            page = self.get_or_create_page(url)
            if url not in page.url:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.bring_to_front()

        try:
            self.with_retry(_execute)
            return True, f"Opened {url}"
        except Exception as e:
            return False, f"Failed to open {url}: {str(e)[:60]}"

    def summarize_page(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """Get page text and summarize with GPT."""
        def _get_text():
            # Use the most recently active page
            self._ensure_browser()
            pages = self._context.pages
            if not pages:
                raise RuntimeError("No open browser pages.")
            page = pages[-1]  # most recent
            return page.inner_text("body")[:6000]

        try:
            page_text = self.with_retry(_get_text)
            style = intent.data.get("style", "bullet")
            summary = self._gpt_summarize(page_text, style)
            return True, f"Page Summary:\n{summary}"
        except Exception as e:
            return False, f"Summarize failed: {str(e)[:80]}"

    def create_notion_task(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        title = intent.target
        description = intent.data.get("description", "")

        if not title:
            return False, "No task title provided."

        def _execute():
            page = self.get_or_create_page("notion.so")
            page.goto(NOTION_NEW_PAGE_URL, wait_until="networkidle", timeout=20000)
            time.sleep(1.0)

            # Type title
            title_el = page.wait_for_selector(SEL_NOTION_TITLE, timeout=10000)
            title_el.click()
            page.keyboard.type(title, delay=30)

            if description:
                page.keyboard.press("Enter")
                time.sleep(0.3)
                page.keyboard.type(description, delay=20)

        try:
            self.with_retry(_execute)
            return True, f"Notion task created: '{title}'"
        except Exception as e:
            return False, f"Notion task creation failed: {str(e)[:80]}"

    def dom_mouse_action(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """
        Perform a small browser interaction grounded in DOM selectors or mouse
        coordinates. This is the generic layer for commands like "click Send",
        "type hello in the search box", or "press Enter".
        """
        action = intent.data.get("action", "").lower()
        selector = intent.data.get("selector", "")
        text = intent.data.get("text", "")
        key = intent.data.get("key", "")
        x = intent.data.get("x")
        y = intent.data.get("y")

        def _execute():
            self._ensure_browser()
            page = self.get_active_page()
            if not page:
                raise RuntimeError("No active browser page.")

            if action == "click":
                if selector:
                    self.safe_click(page, selector)
                elif text:
                    self.click_by_text(page, text)
                elif x is not None and y is not None:
                    self.click_at(page, int(x), int(y))
                else:
                    raise RuntimeError("Click needs a selector, text, or x/y coordinates.")
                return "Clicked browser element."

            if action == "type":
                if selector:
                    self.safe_click(page, selector)
                page.keyboard.type(text, delay=15)
                return "Typed into browser."

            if action == "press":
                page.keyboard.press(key or text or "Enter")
                return "Pressed key in browser."

            raise RuntimeError(f"Unsupported browser action: {action}")

        try:
            message = self.with_retry(_execute)
            return True, message
        except Exception as e:
            return False, f"Browser action failed: {str(e)[:80]}"

    def adaptive_browser_task(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        """
        Bounded observe-plan-act loop for browser tasks.

        Each step observes DOM/app structure, chooses an action, executes with
        resilient DOM/text/mouse helpers, observes again, and verifies progress.
        """
        goal = intent.data.get("goal") or intent.raw_text or intent.target or "complete browser task"
        expected_text = intent.data.get("expected_text", "")
        max_steps = int(intent.data.get("max_steps", 6) or 6)
        max_steps = max(1, min(max_steps, 10))

        try:
            self._ensure_browser()
            page = self.get_active_page()
            if not page:
                raise RuntimeError("No active browser page.")

            completed_steps = []
            previous_fingerprints = set()

            for step_index in range(max_steps):
                dom = self.observe_page(page)
                if self._goal_satisfied(page, dom, goal, expected_text):
                    return True, f"Task complete after {step_index} step(s): {goal}"

                fingerprint = self._dom_fingerprint(dom)
                if fingerprint in previous_fingerprints and step_index > 0:
                    shot = self.capture_screenshot(page, "planner_no_progress")
                    return False, f"Planner stopped: no page progress. screenshot={shot}"
                previous_fingerprints.add(fingerprint)

                action = self._choose_next_action(intent, context, dom, completed_steps, goal)
                
                # ── SMART SCROLLING ─────────────────────────────────────────
                if not action and step_index < max_steps - 1:
                    logger.info("No action found in current viewport. Scrolling down...")
                    page.mouse.wheel(0, 500)
                    time.sleep(0.5)
                    continue # Try again after scrolling

                if not action:
                    shot = self.capture_screenshot(page, "planner_no_action")
                    return False, f"Planner could not choose next action. screenshot={shot}"

                result = self._execute_planned_action(page, action)
                completed_steps.append(f"{action.get('action')}:{result}")
                time.sleep(0.4)

                after_dom = self.observe_page(page)
                if self._goal_satisfied(page, after_dom, goal, expected_text):
                    return True, f"Task complete: {goal} ({len(completed_steps)} step(s))"

            shot = self.capture_screenshot(page, "planner_max_steps")
            return False, f"Planner hit max_steps={max_steps}. steps={completed_steps}. screenshot={shot}"
        except Exception as e:
            logger.exception(f"Adaptive browser task failed: {e}")
            return False, f"Adaptive browser task failed: {str(e)[:100]}"

    def _choose_next_action(
        self,
        intent: IntentResult,
        context: Context,
        dom: dict,
        completed_steps: list[str],
        goal: str,
    ) -> dict:
        explicit = self._explicit_action(intent, completed_steps)
        if explicit:
            return explicit

        llm_action = self._llm_next_action(goal, dom, completed_steps, context.learning_hints)
        if llm_action:
            return llm_action

        return self._heuristic_next_action(goal, dom, completed_steps)

    def _explicit_action(self, intent: IntentResult, completed_steps: list[str]) -> dict:
        if completed_steps:
            return {}
        action = (intent.data.get("action") or "").lower()
        if not action or action == "auto":
            return {}
        return {
            "action": action,
            "selector": intent.data.get("selector", ""),
            "labels": intent.data.get("labels", []),
            "text": intent.data.get("text", ""),
            "key": intent.data.get("key", ""),
            "x": intent.data.get("x"),
            "y": intent.data.get("y"),
        }

    def _llm_next_action(
        self,
        goal: str,
        dom: dict,
        completed_steps: list[str],
        learning_hints: list[str],
    ) -> dict:
        if not has_valid_openai_key():
            return {}
        try:
            dom_summary = {
                "title": dom.get("title", ""),
                "url": dom.get("url", ""),
                "activeElement": dom.get("activeElement", ""),
                "appStructure": dom.get("appStructure", {}),
                "elements": dom.get("elements", [])[:50],
            }
            response = get_openai_client().chat.completions.create(
                model=os.getenv("PLANNER_MODEL", "gpt-4o-mini"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You control a browser through DOM-grounded actions. "
                            "Return JSON only. Choose one next action from: click, type, press, done. "
                            "Prefer labels/text/roles from the DOM. Use selectors only when present in DOM."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({
                            "goal": goal,
                            "completed_steps": completed_steps,
                            "learning_hints": learning_hints[:8],
                            "dom": dom_summary,
                            "output_schema": {
                                "action": "click|type|press|done",
                                "labels": ["visible label text"],
                                "selector": "optional selector",
                                "text": "text to type",
                                "key": "key to press",
                                "reason": "short reason"
                            },
                        })[:9000],
                    },
                ],
                temperature=0.1,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
            if parsed.get("action") == "done":
                return {"action": "done"}
            if parsed.get("action") in {"click", "type", "press"}:
                return parsed
        except Exception as e:
            logger.warning(f"Planner LLM unavailable, falling back to heuristics: {e}")
        return {}

    def _heuristic_next_action(self, goal: str, dom: dict, completed_steps: list[str]) -> dict:
        goal_lower = goal.lower()
        elements = dom.get("elements", [])

        type_text = self._extract_quoted_text(goal)
        if not type_text and "search" in goal_lower:
            type_text = goal.split("search", 1)[-1].replace("for", "", 1).strip(" .:")

        if type_text and not any(step.startswith("type:") for step in completed_steps):
            labels = self._labels_from_goal(goal, prefer_inputs=True)
            if not labels:
                labels = ["Search", "Message Body", "Body", "To", "Recipients"]
            return {"action": "type", "labels": labels, "text": type_text}

        click_labels = self._labels_from_goal(goal, prefer_inputs=False)
        if not click_labels:
            click_labels = self._buttonish_labels(elements)
        if click_labels:
            return {"action": "click", "labels": click_labels[:4]}

        if "enter" in goal_lower:
            return {"action": "press", "key": "Enter"}
        return {}

    def _execute_planned_action(self, page, action: dict) -> str:
        kind = (action.get("action") or "").lower()
        labels = action.get("labels") or []
        if isinstance(labels, str):
            labels = [labels]
        selector = action.get("selector", "")

        if kind == "done":
            return "done"
        if kind == "click":
            if action.get("x") is not None and action.get("y") is not None:
                self.click_at(page, int(action["x"]), int(action["y"]))
                return "mouse_xy"
            return self.click_resilient(page, selectors=[selector] if selector else [], labels=labels)
        if kind == "type":
            text = action.get("text", "")
            if not text:
                raise RuntimeError("type action missing text")
            return self.fill_resilient(
                page,
                value=text,
                selectors=[selector] if selector else [],
                labels=labels,
                press_ctrl_a=bool(action.get("replace", False)),
            )
        if kind == "press":
            page.keyboard.press(action.get("key") or action.get("text") or "Enter")
            self.record_action_event("press", f"key:{action.get('key') or action.get('text') or 'Enter'}", labels, page=page)
            return "key"
        raise RuntimeError(f"Unknown planned action: {kind}")

    def _goal_satisfied(self, page, dom: dict, goal: str, expected_text: str) -> bool:
        """
        Heuristic + Vision check to see if the task is finished.
        """
        # 1. Direct expected text match (Fastest)
        if expected_text:
            try:
                body = page.inner_text("body", timeout=1000).lower()
                if expected_text.lower() in body:
                    return True
            except Exception:
                pass

        # 2. Heuristic keyword match (Medium)
        lowered_goal = goal.lower()
        if any(word in lowered_goal for word in ["send", "sent", "submitted", "created", "post"]):
            try:
                body = page.inner_text("body", timeout=1000).lower()
                if any(word in body for word in ["sent", "submitted", "created", "success", "done", "posted"]):
                    return True
            except Exception:
                pass

        # 3. Vision-based verification (Most reliable for complex UI changes)
        if has_valid_openai_key():
            try:
                shot_path = self.capture_screenshot(page, "verification")
                if shot_path:
                    return self._vision_verify_goal(goal, shot_path)
            except Exception as e:
                logger.warning(f"Vision verification failed: {e}")

        return False

    def _vision_verify_goal(self, goal: str, screenshot_path: str) -> bool:
        """
        Ask GPT-4o-mini vision if the goal is satisfied based on a screenshot.
        """
        import base64
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        try:
            resp = get_openai_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"The user's goal was: '{goal}'. Based on this screenshot, has this goal been successfully completed? Reply with a JSON object: {{\"satisfied\": true/false, \"reason\": \"...\"}}"},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                        ]
                    }
                ],
                max_tokens=100,
                response_format={"type": "json_object"}
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            is_satisfied = bool(parsed.get("satisfied", False))
            if is_satisfied:
                logger.info(f"Vision verified goal: {parsed.get('reason', 'Goal satisfied')}")
            return is_satisfied
        except Exception as e:
            logger.warning(f"Vision API error: {e}")
            return False

    def diagnose_failure(self, goal: str, steps: list[str]) -> str:
        """
        Use Vision to explain WHY a browser task failed.
        """
        if not has_valid_openai_key():
            return "Task failed (Vision diagnosis unavailable)."
            
        page = self.get_active_page()
        if not page:
            return "Task failed (No active browser page)."
            
        shot_path = self.capture_screenshot(page, "failure_diagnosis")
        if not shot_path:
            return "Task failed (Could not capture screenshot for diagnosis)."
            
        import base64
        with open(shot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        try:
            resp = get_openai_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"The browser task failed. Goal: '{goal}'. Steps attempted: {steps}. Based on this screenshot, explain briefly WHY it failed (e.g. button disabled, error message visible, login required)."},
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                        ]
                    }
                ],
                max_tokens=150
            )
            diagnosis = resp.choices[0].message.content.strip()
            logger.info(f"Failure diagnosis: {diagnosis}")
            return diagnosis
        except Exception as e:
            logger.warning(f"Diagnosis API error: {e}")
            return "Task failed (Diagnosis error)."

    def _dom_fingerprint(self, dom: dict) -> str:
        elements = dom.get("elements", [])[:20]
        parts = [dom.get("url", ""), dom.get("title", ""), dom.get("activeElement", "")]
        parts.extend(f"{e.get('selector')}:{e.get('text')}" for e in elements)
        return "|".join(parts)[:2000]

    def _extract_quoted_text(self, goal: str) -> str:
        for quote in ['"', "'"]:
            if quote in goal:
                parts = goal.split(quote)
                if len(parts) >= 3:
                    return parts[1].strip()
        return ""

    def _labels_from_goal(self, goal: str, prefer_inputs: bool) -> list[str]:
        goal_lower = goal.lower()
        labels = []
        if "search" in goal_lower:
            labels.extend(["Search", "Search Wikipedia", "Search input"])
        if "message" in goal_lower or "body" in goal_lower:
            labels.extend(["Message Body", "Body", "Type a message", "Message"])
        if "recipient" in goal_lower or "to " in goal_lower:
            labels.extend(["To", "Recipients"])
        if not prefer_inputs:
            for label in ["Send", "Submit", "Save", "Create", "Continue", "Next", "Search"]:
                if label.lower() in goal_lower:
                    labels.insert(0, label)
        return list(dict.fromkeys(labels))

    def _buttonish_labels(self, elements: list[dict]) -> list[str]:
        labels = []
        for element in elements:
            tag = element.get("tag", "")
            role = element.get("role", "")
            text = element.get("text", "")
            if text and (tag == "button" or role == "button"):
                labels.append(text)
        return labels

    def _gpt_summarize(self, text: str, style: str = "bullet") -> str:
        format_instruction = (
            "in 4-6 concise bullet points" if style == "bullet"
            else "in 2-3 short paragraphs"
        )
        resp = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Summarize the following web page content {format_instruction}. Focus on key information, skip navigation/ads."},
                {"role": "user", "content": text},
            ],
            max_tokens=350,
        )
        return resp.choices[0].message.content.strip()
