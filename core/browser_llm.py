import os
import time
import json
import logging

logger = logging.getLogger(__name__)

SITE_CONFIGS = {
    "chatgpt": {
        "url": "https://chatgpt.com",
        "input_selectors": ["#prompt-textarea", "div[contenteditable='true']", "textarea"],
        "send_selectors": ["button[data-testid='send-button']", "button[aria-label*='Send']"],
        "ready_selectors": ["#prompt-textarea", "div[contenteditable='true']"],
        "stop_indicator": "button[data-testid='stop-button']",
    },
    "claude": {
        "url": "https://claude.ai/new",
        "input_selectors": ["div[contenteditable='true']", "textarea"],
        "send_selectors": ["button[aria-label*='Send']", "button[class*='send']"],
        "ready_selectors": ["div[contenteditable='true']"],
        "stop_indicator": "button:has(svg[class*='stop'])",
    },
    "gemini": {
        "url": "https://gemini.google.com/new",
        "input_selectors": ["div[contenteditable='true']", "textarea"],
        "send_selectors": ["button[aria-label*='Send']", "button[aria-label*='send']"],
        "ready_selectors": ["div[contenteditable='true']"],
        "stop_indicator": "button[aria-label*='Stop']",
    },
    "perplexity": {
        "url": "https://www.perplexity.ai",
        "input_selectors": ["textarea", "input[type='text']"],
        "send_selectors": ["button[aria-label*='Submit']", "button[type='submit']"],
        "ready_selectors": ["textarea"],
        "stop_indicator": None,
    },
    "huggingchat": {
        "url": "https://huggingface.co/chat",
        "input_selectors": ["textarea", "div[contenteditable='true']"],
        "send_selectors": ["button[type='submit']", "button[aria-label*='Send']"],
        "ready_selectors": ["textarea"],
        "stop_indicator": None,
    },
}

RESPONSE_EXTRACTORS = {
    "chatgpt": """
        () => {
            const articles = document.querySelectorAll('div[data-message-author-role="assistant"]');
            if (articles.length === 0) return '';
            const last = articles[articles.length - 1];
            return last.innerText || last.textContent || '';
        }
    """,
    "claude": """
        () => {
            const messages = document.querySelectorAll('div[class*="message"]');
            if (messages.length === 0) return '';
            const last = messages[messages.length - 1];
            return last.innerText || last.textContent || '';
        }
    """,
    "gemini": """
        () => {
            const responses = document.querySelectorAll('div[class*="response"], div[class*="message-content"]');
            if (responses.length === 0) return '';
            const last = responses[responses.length - 1];
            return last.innerText || last.textContent || '';
        }
    """,
    "perplexity": """
        () => {
            const answers = document.querySelectorAll('div[class*="prose"], div[class*="answer"], div[class*="result"]');
            if (answers.length === 0) return '';
            const last = answers[answers.length - 1];
            return last.innerText || last.textContent || '';
        }
    """,
    "huggingchat": """
        () => {
            const messages = document.querySelectorAll('div[class*="message"], article');
            if (messages.length === 0) return '';
            const last = messages[messages.length - 1];
            return last.innerText || last.textContent || '';
        }
    """,
}

COOKIE_SELECTORS = [
    "button:has-text('Accept all')",
    "button:has-text('Accept All')",
    "button:has-text('Accept')",
    "button:has-text('Got it')",
    "button:has-text('Continue')",
    "div[aria-label*='Accept']",
    "button[id*='accept']",
    "button[class*='accept']",
]

SITE_ALIASES = {
    "chatgpt": ["chatgpt", "chatgpt.com", "chat.openai.com", "openai", "gpt", "chat-gpt"],
    "claude": ["claude", "claude.ai", "anthropic"],
    "gemini": ["gemini", "gemini.google.com", "bard", "google"],
    "perplexity": ["perplexity", "perplexity.ai", "pplx"],
    "huggingchat": ["huggingchat", "huggingface", "hf", "huggingface.co/chat"],
}


def _resolve_site(model_name: str) -> str:
    m = model_name.lower().replace(" ", "").replace(".", "")
    for site_key, aliases in SITE_ALIASES.items():
        for alias in aliases:
            a = alias.lower().replace(" ", "").replace(".", "")
            if a in m or m in a:
                return site_key
    return "chatgpt"


def _find_element(cdp, selectors: list[str]) -> str | None:
    for sel in selectors:
        js = f"document.querySelector({json.dumps(sel)}) !== null"
        try:
            if cdp.evaluate(js):
                return sel
        except Exception:
            continue
    return None


def _wait_for_selector(cdp, selectors: list[str], timeout: float = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in selectors:
            js = f"document.querySelector({json.dumps(sel)}) !== null"
            try:
                if cdp.evaluate(js):
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _dismiss_cookies(cdp):
    for sel in COOKIE_SELECTORS:
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(sel)});
            if (el) {{ el.click(); return true; }}
            return false;
        }})()
        """
        try:
            if cdp.evaluate(js):
                logger.info(f"Dismissed cookie modal via: {sel}")
                time.sleep(0.5)
                return
        except Exception:
            continue


def _type_into_input(cdp, selector: str, text: str) -> bool:
    try:
        cdp.send("Runtime.evaluate", {
            "expression": f"document.querySelector({json.dumps(selector)}).focus()",
        })
        time.sleep(0.2)
        cdp.send("Input.insertText", {"text": text})
        return True
    except Exception as e:
        logger.warning(f"BrowserLLM type failed: {e}")
        return False


def _press_send(cdp, send_selectors: list[str]):
    for sel in send_selectors:
        js = f"""
        (() => {{
            const btn = document.querySelector({json.dumps(sel)});
            if (btn && !btn.disabled) {{ btn.click(); return true; }}
            return false;
        }})()
        """
        try:
            if cdp.evaluate(js):
                logger.info(f"Clicked send via: {sel}")
                return
        except Exception:
            continue
    cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "windowsVirtualKeyCode": 13})
    cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyUp", "key": "Enter", "windowsVirtualKeyCode": 13})


def _wait_for_response(cdp, config: dict, timeout: float = 90) -> str:
    site_name = config.get("_site_name", "chatgpt")
    extractor = RESPONSE_EXTRACTORS.get(site_name)
    stop_sel = config.get("stop_indicator")
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0

    while time.time() < deadline:
        if stop_sel:
            js = f"document.querySelector({json.dumps(stop_sel)}) !== null"
            try:
                generating = cdp.evaluate(js)
            except Exception:
                generating = False
        else:
            generating = True

        if extractor:
            try:
                current = cdp.evaluate(extractor) or ""
                if current and current != last_text:
                    last_text = current
                    stable_count = 0
                elif current and current == last_text and not generating:
                    stable_count += 1
                    if stable_count >= 3:
                        return current.strip()
                elif not generating and current:
                    return current.strip()
            except Exception:
                pass

        time.sleep(1.0)

    return (last_text or "").strip()


def call_llm(model_name: str, system_prompt: str, user_message: str) -> str:
    from executors.base_executor import BaseExecutor

    site = _resolve_site(model_name)
    config = dict(SITE_CONFIGS.get(site, SITE_CONFIGS["chatgpt"]))
    config["_site_name"] = site
    url = config["url"]

    logger.info(f"BrowserLLM: Using '{site}' ({url}) for LLM call")

    try:
        BaseExecutor._ensure_browser()
        cdp = BaseExecutor._cdp
        if not cdp:
            return "Browser is not available for LLM call."
    except Exception as e:
        return f"Failed to launch browser: {e}"

    try:
        BaseExecutor.navigate(url, wait=True)
        time.sleep(2.0)
    except Exception as e:
        return f"Failed to navigate to {url}: {e}"

    _dismiss_cookies(cdp)

    if not _wait_for_selector(cdp, config["ready_selectors"], timeout=20):
        return f"Timed out waiting for {site} to load. The page may need manual login."

    input_sel = _find_element(cdp, config["input_selectors"])
    if not input_sel:
        return f"Could not find input field on {site}."

    full_prompt = f"{system_prompt}\n\n{user_message}" if system_prompt else user_message
    if not _type_into_input(cdp, input_sel, full_prompt):
        return "Failed to type prompt into input field."

    time.sleep(0.5)
    _press_send(cdp, config["send_selectors"])

    response = _wait_for_response(cdp, config, timeout=90)

    if response:
        return response

    # Fallback: try to get page text as last resort
    try:
        body = cdp.evaluate("document.body.innerText") or ""
        lines = [l.strip() for l in body.split("\n") if l.strip()]
        return "\n".join(lines[-50:])
    except Exception:
        pass

    return "No response generated by the browser LLM."
