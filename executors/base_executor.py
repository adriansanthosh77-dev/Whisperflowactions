"""
base_executor.py — Shared Playwright browser instance + retry utilities.
"""

import os
import time
import logging
from pathlib import Path
from typing import Optional, Callable
from playwright.sync_api import (
    sync_playwright, Browser, BrowserContext, Page, Playwright, TimeoutError as PWTimeout
)
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

BROWSER_PROFILE = os.getenv("BROWSER_PROFILE_PATH", "")
RECORD_VIDEO_DIR = os.getenv("RECORD_VIDEO_DIR", "").strip()
RECORD_TRACE_DIR = os.getenv("RECORD_TRACE_DIR", "").strip()
DEFAULT_TIMEOUT_MS = 8000
MAX_RETRIES = 3
MAX_DOM_ELEMENTS = 80
SCREENSHOT_DIR = Path("data/screenshots")


class BaseExecutor:
    """
    Manages a persistent Playwright Chromium instance.
    All executors share the same browser/context to maintain login sessions.
    """
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _context: Optional[BrowserContext] = None
    _action_events: list[dict] = []

    @classmethod
    def _ensure_browser(cls):
        if cls._browser and cls._browser.is_connected():
            return
        logger.info("Launching Playwright Chromium...")
        cls._playwright = sync_playwright().start()
        launch_kwargs = dict(
            headless=False,   # must be False to interact with web apps
            args=["--disable-blink-features=AutomationControlled"],
        )
        context_kwargs = {}
        if RECORD_VIDEO_DIR:
            Path(RECORD_VIDEO_DIR).mkdir(parents=True, exist_ok=True)
            context_kwargs["record_video_dir"] = RECORD_VIDEO_DIR

        if BROWSER_PROFILE:
            cls._context = cls._playwright.chromium.launch_persistent_context(
                BROWSER_PROFILE, **launch_kwargs, **context_kwargs
            )
            cls._browser = cls._context.browser
        else:
            cls._browser = cls._playwright.chromium.launch(**launch_kwargs)
            cls._context = cls._browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                **context_kwargs,
            )
        if RECORD_TRACE_DIR:
            Path(RECORD_TRACE_DIR).mkdir(parents=True, exist_ok=True)
            cls._context.tracing.start(screenshots=True, snapshots=True, sources=True)

    @classmethod
    def get_or_create_page(cls, url_contains: str) -> Page:
        """
        Return existing page matching url_contains, or open a new tab.
        """
        cls._ensure_browser()
        for page in cls._context.pages:
            if url_contains in page.url:
                page.bring_to_front()
                return page
        page = cls._context.new_page()
        return page

    @classmethod
    def get_active_page(cls) -> Optional[Page]:
        """
        Return the most recently used browser page, if Playwright is running.
        """
        if not cls._context or not cls._context.pages:
            return None
        try:
            page = cls._context.pages[-1]
            page.bring_to_front()
            return page
        except Exception:
            return cls._context.pages[-1]

    @classmethod
    def observe_active_page(cls) -> dict:
        """
        Capture structured page state for reasoning. This intentionally uses DOM
        metadata and element boxes instead of screenshots so actions can be
        grounded in selectors and coordinates.
        """
        page = cls.get_active_page()
        if not page:
            return {}
        return cls.observe_page(page)

    @staticmethod
    def observe_page(page: Page, limit: int = MAX_DOM_ELEMENTS) -> dict:
        js = """
        (limit) => {
          const selectorFor = (el) => {
            if (el.id) return `#${CSS.escape(el.id)}`;
            const attrs = ["data-testid", "aria-label", "name", "placeholder", "title"];
            for (const attr of attrs) {
              const value = el.getAttribute(attr);
              if (value) return `${el.tagName.toLowerCase()}[${attr}="${CSS.escape(value)}"]`;
            }
            const role = el.getAttribute("role");
            if (role) return `${el.tagName.toLowerCase()}[role="${CSS.escape(role)}"]`;
            return el.tagName.toLowerCase();
          };

          const isVisible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 &&
              style.visibility !== "hidden" && style.display !== "none";
          };

          const textOf = (el, max = 160) =>
            (el.innerText || el.value || el.getAttribute("aria-label") ||
             el.getAttribute("placeholder") || el.getAttribute("title") || "")
              .trim().replace(/\\s+/g, " ").slice(0, max);

          const boxOf = (el) => {
            const rect = el.getBoundingClientRect();
            return {
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              width: Math.round(rect.width),
              height: Math.round(rect.height)
            };
          };

          const itemOf = (el, index) => ({
            index,
            tag: el.tagName.toLowerCase(),
            selector: selectorFor(el),
            role: el.getAttribute("role") || "",
            text: textOf(el, 120),
            bbox: boxOf(el)
          });

          const candidates = Array.from(document.querySelectorAll(
            'a, button, input, textarea, select, [role="button"], [role="link"], [contenteditable="true"], [aria-label], [data-testid]'
          ));
          const headings = Array.from(document.querySelectorAll("h1,h2,h3,[role='heading']"))
            .filter(isVisible).slice(0, 20).map(itemOf);
          const landmarks = Array.from(document.querySelectorAll("header,nav,main,aside,footer,section,form,[role='main'],[role='navigation'],[role='banner'],[role='form'],[role='search']"))
            .filter(isVisible).slice(0, 30).map((el, index) => ({
              ...itemOf(el, index),
              childText: textOf(el, 260)
            }));
          const forms = Array.from(document.querySelectorAll("form,[role='form'],[role='search']"))
            .filter(isVisible).slice(0, 12).map((el, index) => ({
              ...itemOf(el, index),
              controls: Array.from(el.querySelectorAll("input,textarea,button,[contenteditable='true']"))
                .filter(isVisible).slice(0, 20).map(itemOf)
            }));
          const topSections = Array.from(document.querySelectorAll("header,main,section,[role='main']"))
            .filter(isVisible)
            .filter((el) => el.getBoundingClientRect().top < innerHeight * 0.9)
            .slice(0, 8).map((el, index) => ({
              ...itemOf(el, index),
              childText: textOf(el, 500)
            }));

          return {
            title: document.title,
            url: location.href,
            activeElement: selectorFor(document.activeElement),
            viewport: { width: innerWidth, height: innerHeight },
            appStructure: { headings, landmarks, forms, topSections },
            elements: candidates.filter(isVisible).slice(0, limit).map(itemOf)
          };
        }
        """
        try:
            return page.evaluate(js, limit)
        except Exception as e:
            logger.debug(f"DOM observation failed: {e}")
            return {"url": page.url, "error": str(e)[:120]}

    @staticmethod
    def capture_screenshot(page: Page, label: str = "page") -> str:
        """
        Save a screenshot for failed actions/debugging. The system still reasons
        from DOM first; screenshots are evidence for the learning loop.
        """
        try:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            safe_label = "".join(ch if ch.isalnum() else "_" for ch in label.lower())[:40]
            path = SCREENSHOT_DIR / f"{int(time.time())}_{safe_label}.png"
            page.screenshot(path=str(path), full_page=False)
            return str(path)
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return ""

    @classmethod
    def record_action_event(
        cls,
        action: str,
        strategy: str,
        labels: list[str] | None = None,
        selectors: list[str] | None = None,
        success: bool = True,
        error: str = "",
        page: Page | None = None,
        screenshot: str = "",
    ):
        cls._action_events.append({
            "timestamp": int(time.time()),
            "action": action,
            "strategy": strategy,
            "labels": labels or [],
            "selectors": selectors or [],
            "success": success,
            "error": error[:200],
            "url": page.url if page else "",
            "title": page.title() if page else "",
            "screenshot": screenshot,
        })

    @classmethod
    def consume_action_events(cls) -> list[dict]:
        events = cls._action_events[:]
        cls._action_events.clear()
        return events

    @classmethod
    def find_dom_match(cls, page: Page, labels: list[str], tags: list[str] | None = None) -> dict:
        dom = cls.observe_page(page)
        elements = dom.get("elements", [])
        if not labels:
            return {}

        lowered = [label.lower() for label in labels if label]
        allowed_tags = set(tags or [])
        best = {}
        best_score = 0
        for element in elements:
            if allowed_tags and element.get("tag") not in allowed_tags:
                continue
            haystack = " ".join([
                element.get("text", ""),
                element.get("selector", ""),
                element.get("role", ""),
            ]).lower()
            score = 0
            for label in lowered:
                if label and label in haystack:
                    score += len(label)
            if score > best_score:
                best = element
                best_score = score
        return best

    @classmethod
    def click_resilient(
        cls,
        page: Page,
        selectors: list[str] | None = None,
        labels: list[str] | None = None,
        timeout: int = DEFAULT_TIMEOUT_MS,
    ) -> str:
        selectors = selectors or []
        labels = labels or []
        errors = []

        for selector in selectors:
            try:
                cls.safe_click(page, selector, timeout=timeout)
                strategy = f"selector:{selector}"
                cls.record_action_event("click", strategy, labels, selectors, page=page)
                return strategy
            except Exception as e:
                errors.append(f"{selector}: {str(e)[:80]}")

        for label in labels:
            try:
                page.get_by_role("button", name=label).first.click(timeout=timeout)
                strategy = f"role_button:{label}"
                cls.record_action_event("click", strategy, labels, selectors, page=page)
                return strategy
            except Exception as e:
                errors.append(f"button {label}: {str(e)[:80]}")
            try:
                page.get_by_text(label, exact=False).first.click(timeout=timeout)
                strategy = f"text:{label}"
                cls.record_action_event("click", strategy, labels, selectors, page=page)
                return strategy
            except Exception as e:
                errors.append(f"text {label}: {str(e)[:80]}")

        match = cls.find_dom_match(page, labels)
        bbox = match.get("bbox", {})
        if bbox:
            x = bbox["x"] + max(1, bbox["width"] // 2)
            y = bbox["y"] + max(1, bbox["height"] // 2)
            page.mouse.click(x, y)
            strategy = f"dom_mouse:{match.get('selector', '')}"
            cls.record_action_event("click", strategy, labels, selectors, page=page)
            return strategy

        shot = cls.capture_screenshot(page, "click_failed")
        cls.record_action_event(
            "click", "failed", labels, selectors, success=False,
            error="Could not click via selectors/DOM", page=page, screenshot=shot
        )
        raise RuntimeError(f"Could not click via selectors/DOM. screenshot={shot} errors={errors[-3:]}")

    @classmethod
    def fill_resilient(
        cls,
        page: Page,
        value: str,
        selectors: list[str] | None = None,
        labels: list[str] | None = None,
        timeout: int = DEFAULT_TIMEOUT_MS,
        press_ctrl_a: bool = True,
    ) -> str:
        selectors = selectors or []
        labels = labels or []
        errors = []

        for selector in selectors:
            try:
                page.wait_for_selector(selector, state="visible", timeout=timeout)
                page.click(selector)
                if press_ctrl_a:
                    page.keyboard.press("Control+A")
                page.keyboard.type(value, delay=20)
                strategy = f"selector:{selector}"
                cls.record_action_event("fill", strategy, labels, selectors, page=page)
                return strategy
            except Exception as e:
                errors.append(f"{selector}: {str(e)[:80]}")

        for label in labels:
            for role in ("textbox", "combobox"):
                try:
                    locator = page.get_by_role(role, name=label).first
                    locator.click(timeout=timeout)
                    if press_ctrl_a:
                        page.keyboard.press("Control+A")
                    page.keyboard.type(value, delay=20)
                    strategy = f"role_{role}:{label}"
                    cls.record_action_event("fill", strategy, labels, selectors, page=page)
                    return strategy
                except Exception as e:
                    errors.append(f"{role} {label}: {str(e)[:80]}")

        match = cls.find_dom_match(page, labels, tags=["input", "textarea", "div"])
        bbox = match.get("bbox", {})
        if bbox:
            x = bbox["x"] + max(1, bbox["width"] // 2)
            y = bbox["y"] + max(1, bbox["height"] // 2)
            page.mouse.click(x, y)
            if press_ctrl_a:
                page.keyboard.press("Control+A")
            page.keyboard.type(value, delay=20)
            strategy = f"dom_mouse:{match.get('selector', '')}"
            cls.record_action_event("fill", strategy, labels, selectors, page=page)
            return strategy

        shot = cls.capture_screenshot(page, "fill_failed")
        cls.record_action_event(
            "fill", "failed", labels, selectors, success=False,
            error="Could not fill via selectors/DOM", page=page, screenshot=shot
        )
        raise RuntimeError(f"Could not fill via selectors/DOM. screenshot={shot} errors={errors[-3:]}")

    @staticmethod
    def get_mouse_position() -> dict:
        try:
            import ctypes

            class Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

            point = Point()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            return {"x": int(point.x), "y": int(point.y)}
        except Exception as e:
            logger.debug(f"Mouse position unavailable: {e}")
            return {}

    @classmethod
    def close(cls):
        if cls._context and RECORD_TRACE_DIR:
            try:
                trace_path = Path(RECORD_TRACE_DIR) / f"{int(time.time())}_trace.zip"
                cls._context.tracing.stop(path=str(trace_path))
            except Exception as e:
                logger.debug(f"Trace stop failed: {e}")
        if cls._browser:
            cls._browser.close()
        if cls._playwright:
            cls._playwright.stop()

    # ── Retry utility ──────────────────────────────────────────────────────

    @staticmethod
    def with_retry(fn: Callable, retries: int = MAX_RETRIES, delay: float = 1.0):
        """
        Execute fn(), retrying on failure up to `retries` times.
        Returns result or raises last exception.
        """
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                return fn()
            except (PWTimeout, Exception) as e:
                last_exc = e
                logger.warning(f"Attempt {attempt}/{retries} failed: {e}")
                if attempt < retries:
                    time.sleep(delay)
        raise last_exc

    # ── Safe element helpers ───────────────────────────────────────────────

    @staticmethod
    def safe_click(page: Page, selector: str, timeout: int = DEFAULT_TIMEOUT_MS):
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        page.click(selector)

    @staticmethod
    def safe_fill(page: Page, selector: str, value: str, timeout: int = DEFAULT_TIMEOUT_MS):
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        page.fill(selector, value)

    @staticmethod
    def safe_text(page: Page, selector: str, timeout: int = DEFAULT_TIMEOUT_MS) -> str:
        page.wait_for_selector(selector, state="visible", timeout=timeout)
        return page.inner_text(selector).strip()

    @staticmethod
    def click_by_text(page: Page, text: str, timeout: int = DEFAULT_TIMEOUT_MS):
        page.get_by_text(text, exact=False).first.click(timeout=timeout)

    @staticmethod
    def click_at(page: Page, x: int, y: int):
        page.mouse.click(x, y)
