"""
base_executor.py — Isolated browser automation via CDP.

Launches a SEPARATE browser instance with its own profile.
Never touches the user's existing browser windows or tabs.
Supports Obscura (stealth/Windows) and headful Chrome (visible/all OSes).
"""

import os
import time
import json
import logging
import threading
import subprocess
import shutil
import socket
import re
import requests
from pathlib import Path
from typing import Optional, Any, Callable
from core.block_detector import BlockDetector
from core.action_memory import ActionMemory
from executors.verification import VerificationEngine
from core.vision_engine import get_vision_engine
from core.platform_utils import IS_WINDOWS, IS_MAC, IS_LINUX

logger = logging.getLogger(__name__)

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
OBSCURA_PORT = int(os.getenv("OBSCURA_PORT", "9222"))
OBSCURA_BIN = os.getenv("OBSCURA_BIN", "obscura.exe")
SCREENSHOT_DIR = Path("data/screenshots")
MAX_DOM_ELEMENTS = 40
BROWSER_PROFILE_DIR = Path("data/browser_profile/jarvis_profile")

class CDPClient:
    """Minimalistic CDP client using sync requests/websockets for Obscura."""
    def __init__(self, port=9222):
        self.port = port
        self.ws_url = None
        self._msg_id = 0
        self._ws = None
        self.lock = threading.Lock()

    def is_alive(self) -> bool:
        """Check if the CDP server is responsive."""
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=1)
            return resp.ok
        except Exception:
            return False

    def connect(self, max_depth: int = 3):
        """Iteratively connects to the best available CDP target."""
        import websockets.sync.client as ws_client
        
        current_depth = 0
        while current_depth < max_depth:
            current_depth += 1
            try:
                # 1. Get targets
                resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=3)
                targets = resp.json()
                
                # Filter for valid page targets
                pages = [t for t in targets if t.get("type") == "page" and not t.get("url", "").startswith("chrome-extension")]
                
                if pages:
                    # Found a page, connect to it
                    target = pages[0]
                    self.ws_url = target.get("webSocketDebuggerUrl")
                    logger.info(f"Connecting to page: {target.get('url')}")
                    
                    if self._ws: self.close()
                    self._ws = ws_client.connect(self.ws_url, close_timeout=2)
                    return True
                
                # 2. No pages? Try browser target
                resp_v = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=2)
                self.ws_url = resp_v.json().get("webSocketDebuggerUrl")
                
                if self.ws_url:
                    logger.info("Connecting to browser target...")
                    if self._ws: self.close()
                    self._ws = ws_client.connect(self.ws_url, close_timeout=2)
                    
                    # Create a page and loop to connect to it
                    logger.info("No active pages found. Creating new target...")
                    # Send direct to avoid recursion with self.send()
                    payload = {"id": 999, "method": "Target.createTarget", "params": {"url": "about:blank"}}
                    self._ws.send(json.dumps(payload))
                    time.sleep(1.0)
                    continue # Loop back to find the new page
                
                raise RuntimeError("No WebSocket URL found.")
                
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
                err_str = str(e).lower()
                is_refused = "10061" in err_str or "refused" in err_str
                
                if is_refused:
                    logger.info(f"CDP port {self.port} is closed. Skipping retries.")
                    return False
                
                logger.warning(f"CDP connection attempt {current_depth} failed: {e}")
                if current_depth >= max_depth: return False
                time.sleep(0.5) # Reduced sleep
        return False

    def send(self, method: str, params: dict = None) -> dict:
        with self.lock:
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    if not self._ws:
                        if not self.connect(): return {}
                    
                    self._msg_id += 1
                    payload = {
                        "id": self._msg_id,
                        "method": method,
                        "params": params or {}
                    }
                    self._ws.send(json.dumps(payload))
                    
                    start_time = time.time()
                    while True:
                        if time.time() - start_time > 5.0:
                            raise RuntimeError(f"CDP timeout for {method}")
                        try:
                            raw = self._ws.recv(timeout=1.0)
                            resp = json.loads(raw)
                            if resp.get("id") == self._msg_id:
                                if "error" in resp:
                                    err = resp["error"].get("message", str(resp["error"]))
                                    raise RuntimeError(f"CDP Error ({method}): {err}")
                                return resp.get("result", {})
                        except TimeoutError:
                            continue
                except Exception as e:
                    err_msg = str(e).lower()
                    is_connection_error = any(x in err_msg for x in ["close frame", "connection closed", "broken pipe", "timeout"])
                    
                    if attempt < max_retries and is_connection_error:
                        logger.warning(f"CDP connection lost during {method}. Retrying ({attempt+1}/{max_retries})...")
                        self.close()
                        time.sleep(1.0)
                        continue
                    
                    if "CDP Error" in str(e): raise
                    logger.error(f"CDP failure ({method}): {e}")
                    raise RuntimeError(f"CDP connection failed: {e}")
            return {}

    def evaluate(self, expression: str, retries: int = 3) -> Any:
        for i in range(retries):
            try:
                res = self.send("Runtime.evaluate", {
                    "expression": expression,
                    "returnByValue": True,
                    "awaitPromise": True
                })
                return res.get("result", {}).get("value")
            except Exception as e:
                err = str(e).lower()
                if i < retries - 1 and any(x in err for x in ["context was destroyed", "navigated", "no such target"]):
                    time.sleep(0.5)
                    continue
                raise
        return None

    def close(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

class BaseExecutor:
    _cdp: Optional[CDPClient] = None
    _last_url = ""
    _abort_execution = False
    _action_events: list[dict] = []
    _block_detector = BlockDetector()
    _block_handler: Optional[Callable] = None
    _action_memory = ActionMemory()
    _teach_events: list[dict] = []
    _teach_last_url = ""
    _verifier: Optional[VerificationEngine] = None
    _state_lock = threading.Lock()

    @classmethod
    def consume_action_events(cls) -> list[dict]:
        with cls._state_lock:
            events = cls._action_events[:]
            cls._action_events.clear()
        return events

    @classmethod
    def start_teach_capture(cls):
        cls._ensure_browser()
        cls._teach_events = []
        cls._teach_last_url = cls.get_active_page_url_safe()
        if cls._teach_last_url:
            cls._teach_events.append({"type": "navigate", "url": cls._teach_last_url})
        cls._inject_teach_capture()

    @classmethod
    def poll_teach_capture(cls):
        cls._ensure_browser()
        current_url = cls.get_active_page_url_safe()
        if current_url and current_url != cls._teach_last_url:
            cls._teach_last_url = current_url
            cls._teach_events.append({"type": "navigate", "url": current_url})
            cls._inject_teach_capture()
        cls._teach_events.extend(cls._drain_teach_events())

    @classmethod
    def stop_teach_capture(cls) -> list[dict]:
        try:
            cls.poll_teach_capture()
        except Exception:
            pass
        return cls._compress_teach_events(cls._teach_events)

    @classmethod
    def _inject_teach_capture(cls):
        js = """
        (() => {
          if (window.__jarvisTeachInstalled) return true;
          window.__jarvisTeachInstalled = true;
          window.__jarvisTeachEvents = window.__jarvisTeachEvents || [];
          const sensitive = (el) => {
            const hay = [
              el.type, el.name, el.id, el.placeholder,
              el.getAttribute("aria-label"), el.autocomplete
            ].filter(Boolean).join(" ").toLowerCase();
            return /password|passcode|otp|card|credit|cvv|cvc|security code|secret|token/.test(hay);
          };
          const cssEscape = (value) => {
            if (window.CSS && CSS.escape) return CSS.escape(value);
            return value.replace(/["\\\\#.;:[\\]>+~*^$|=\\s]/g, "\\\\$&");
          };
          const quoteValue = (value) => value.replace(/["\\\\]/g, "\\\\$&");
          const selectorFor = (el) => {
            const tag = el.tagName.toLowerCase();
            if (el.id) return "#" + cssEscape(el.id);
            for (const attr of ["aria-label", "placeholder", "name", "title"]) {
              const value = el.getAttribute(attr);
              if (value) return `${tag}[${attr}="${quoteValue(value)}"]`;
            }
            const parent = el.parentElement;
            if (!parent) return tag;
            const siblings = Array.from(parent.children).filter(child => child.tagName === el.tagName);
            const index = siblings.indexOf(el) + 1;
            return `${tag}:nth-of-type(${Math.max(index, 1)})`;
          };
          const textOf = (el) => (
            el.innerText || el.value || el.getAttribute("aria-label") ||
            el.getAttribute("placeholder") || el.getAttribute("name") || ""
          ).trim().slice(0, 120);
          document.addEventListener("click", (ev) => {
            const el = ev.target.closest("a,button,input,textarea,[role='button'],[contenteditable='true']");
            if (!el) return;
            const origOutline = el.style.outline;
            const origOutlineOffset = el.style.outlineOffset;
            el.style.outline = "2px solid #9C27B0";
            el.style.outlineOffset = "2px";
            setTimeout(() => {
              el.style.outline = origOutline;
              el.style.outlineOffset = origOutlineOffset;
            }, 600);
            window.__jarvisTeachEvents.push({
              type: "click",
              selector: selectorFor(el),
              label: textOf(el),
              url: location.href,
              ts: Date.now()
            });
          }, true);
          document.addEventListener("change", (ev) => {
            const el = ev.target;
            if (!el || !("value" in el || el.isContentEditable)) return;
            if (sensitive(el)) {
              window.__jarvisTeachEvents.push({
                type: "sensitive_input",
                selector: selectorFor(el),
                label: textOf(el),
                url: location.href,
                ts: Date.now()
              });
              return;
            }
            window.__jarvisTeachEvents.push({
              type: "fill",
              selector: selectorFor(el),
              value: el.isContentEditable ? el.innerText : el.value,
              label: textOf(el),
              url: location.href,
              ts: Date.now()
            });
          }, true);
          document.addEventListener("keydown", (ev) => {
            if (!["Enter", "Tab", "Escape"].includes(ev.key)) return;
            window.__jarvisTeachEvents.push({
              type: "press",
              key: ev.key,
              url: location.href,
              ts: Date.now()
            });
          }, true);
          return true;
        })()
        """
        try:
            cls._cdp.evaluate(js)
        except Exception as e:
            logger.debug("Teach capture injection failed: %s", e)

    @classmethod
    def _drain_teach_events(cls) -> list[dict]:
        js = """
        (() => {
          const events = window.__jarvisTeachEvents || [];
          window.__jarvisTeachEvents = [];
          return events;
        })()
        """
        try:
            events = cls._cdp.evaluate(js)
            return events if isinstance(events, list) else []
        except Exception:
            return []

    @classmethod
    def _compress_teach_events(cls, events: list[dict]) -> list[dict]:
        compressed: list[dict] = []
        last_fill_by_selector: dict[str, int] = {}
        for event in events:
            event_type = event.get("type")
            if event_type == "sensitive_input":
                compressed.append({
                    "type": "needs_user",
                    "reason": "Sensitive field encountered; user must fill it manually.",
                    "selector": event.get("selector", ""),
                })
                continue
            if event_type == "fill":
                selector = event.get("selector", "")
                if selector in last_fill_by_selector:
                    compressed[last_fill_by_selector[selector]] = event
                else:
                    last_fill_by_selector[selector] = len(compressed)
                    compressed.append(event)
                continue
            if event_type == "navigate" and compressed and compressed[-1].get("type") == "navigate":
                compressed[-1] = event
                continue
            if event_type in ("navigate", "click", "press"):
                compressed.append(event)
        return compressed

    @classmethod
    def toggle_stealth_mode(cls, enabled: bool):
        """Toggle between Background (Obscura) and Visual (Headful) browser."""
        os.environ["USE_OBSCURA"] = "true" if enabled else "false"
        logger.info(f"Stealth Mode set to: {enabled}")
        # Reset CDP to force re-connection with new mode next time _ensure_browser is called
        cls.close()

    @classmethod
    def set_block_handler(cls, handler: Optional[Callable]):
        cls._block_handler = handler

    @classmethod
    def check_for_block(cls) -> tuple[bool, str]:
        try:
            dom = cls.observe_active_page()
            blocked, reason = cls._block_detector.is_blocked(dom)
            if not blocked:
                return False, ""

            sensitive = cls._block_detector.is_sensitive_block(dom)
            if sensitive:
                if cls._block_handler:
                    user_handled = cls._block_handler(reason)
                    if user_handled:
                        return False, ""
                return True, reason

            cls._auto_dismiss_block()
            return False, ""
        except Exception as e:
            logger.debug(f"Block check failed: {e}")
            return False, ""

    @classmethod
    def _auto_dismiss_block(cls):
        try:
            dismiss_selectors = [
                "button:has-text('Accept all')", "button:has-text('Accept All')",
                "button:has-text('Accept')", "button:has-text('Allow')",
                "button:has-text('Continue')", "button:has-text('Got it')",
                "button[id*='accept']", "button[class*='accept']",
                "button[aria-label*='Accept']", "button[aria-label*='Dismiss']",
                "button[aria-label*='Close']", "div[aria-label*='Accept']",
                ".fc-cta-consume", ".fc-button.fc-cta-consume",
            ]
            for sel in dismiss_selectors:
                js = f"""
                (() => {{
                    const el = document.querySelector({json.dumps(sel)});
                    if (el && el.offsetParent !== null) {{ el.click(); return true; }}
                    return false;
                }})()
                """
                try:
                    if cls._cdp and cls._cdp.evaluate(js):
                        logger.info(f"Auto-dismissed block via: {sel}")
                        time.sleep(0.3)
                        return
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"Auto-dismiss failed: {e}")

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
    def _get_browser_paths(cls) -> list[tuple[str, str]]:
        paths = []
        configured = os.getenv("BROWSER_EXECUTABLE_PATH", "").strip()
        if configured:
            paths.append((configured, "Configured"))
        if IS_WINDOWS:
            try:
                import winreg
                prog_path = r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, prog_path) as key:
                    prog_id, _ = winreg.QueryValueEx(key, "ProgId")
                cmd_path = fr"{prog_id}\shell\open\command"
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, cmd_path) as key:
                    cmd, _ = winreg.QueryValueEx(key, None)
                match = re.search(r'"([^"]+)"', cmd)
                if match:
                    paths.append((match.group(1), "Default"))
            except Exception:
                pass
            paths += [
                (r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", "Brave"),
                (r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe", "Brave"),
                (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Chrome"),
                (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Chrome"),
                (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Edge"),
            ]
        elif IS_MAC:
            paths += [
                ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "Chrome"),
                ("/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", "Brave"),
                ("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge", "Edge"),
            ]
        elif IS_LINUX:
            for name in ["google-chrome", "chromium-browser", "chromium", "brave-browser"]:
                p = shutil.which(name)
                if p:
                    paths.append((p, name))
        return [(p, n) for p, n in paths if p and os.path.exists(p)]

    @classmethod
    def _ensure_browser(cls, force: bool = True):
        if cls._cdp and not cls._cdp.is_alive():
            logger.warning("CDP stale, resetting...")
            cls.close()

        if not cls._cdp:
            cls._cdp = CDPClient(port=OBSCURA_PORT)
            connected = cls._cdp.connect()

            stealth_mode = os.getenv("USE_OBSCURA", "false").lower() == "true"

            if connected:
                is_obscura = False
                try:
                    resp = requests.get(f"http://127.0.0.1:{OBSCURA_PORT}/json/version", timeout=1)
                    is_obscura = "Obscura" in resp.json().get("Browser", "")
                except Exception:
                    pass

                if stealth_mode and not is_obscura:
                    logger.info("Stealth mode: switching to Obscura")
                    cls.close()
                    connected = False
                elif not stealth_mode and is_obscura:
                    logger.info("Visible mode: switching to headful browser")
                    cls.close()
                    connected = False

            if connected:
                if not cls._verifier:
                    cls._verifier = VerificationEngine(cls._cdp)
                else:
                    cls._verifier.cdp = cls._cdp
                return

            if not force:
                return

            stealth_mode = os.getenv("USE_OBSCURA", "false").lower() == "true"
            if stealth_mode:
                logger.info("Stealth mode: starting Obscura...")
                if cls._start_obscura():
                    cls._cdp = CDPClient(port=OBSCURA_PORT)
                    if cls._cdp.connect():
                        cls._verifier = VerificationEngine(cls._cdp)
                        return
                raise RuntimeError("Obscura failed to start")

            logger.info("Launching isolated browser...")
            browsers = cls._get_browser_paths()
            if not browsers:
                logger.warning("No Chromium browser found. Trying Obscura as fallback...")
                if cls._start_obscura():
                    cls._cdp = CDPClient(port=OBSCURA_PORT)
                    if cls._cdp.connect():
                        cls._verifier = VerificationEngine(cls._cdp)
                        return
                raise RuntimeError(
                    "No Chromium browser or Obscura found. "
                    "Please install Chrome, Brave, or Edge."
                )

            for found_path, name in browsers:
                logger.info(f"Launching {name}: {found_path}")
                BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
                flags = [
                    found_path,
                    f"--remote-debugging-port={OBSCURA_PORT}",
                    "--remote-debugging-address=127.0.0.1",
                    f"--user-data-dir={BROWSER_PROFILE_DIR.resolve()}",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-background-networking",
                    "--disable-component-update",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--mute-audio",
                    "--no-pings",
                ]
                if IS_WINDOWS:
                    flags.append("--disable-gpu")
                try:
                    popen_kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
                    if IS_WINDOWS:
                        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                    subprocess.Popen(flags, **popen_kwargs)
                    if cls._wait_for_cdp(timeout=12):
                        cls._cdp = CDPClient(port=OBSCURA_PORT)
                        if cls._cdp.connect():
                            cls._verifier = VerificationEngine(cls._cdp)
                            return
                    else:
                        logger.warning(f"{name} launched but CDP not responding on port {OBSCURA_PORT}")
                except Exception as e:
                    logger.warning(f"Failed to launch {name}: {e}")
                    continue

            raise RuntimeError(
                f"Could not launch any browser on port {OBSCURA_PORT}. "
                "Is a Chromium-based browser installed?"
            )

    @classmethod
    def _start_obscura(cls) -> bool:
        obscura_path = Path(OBSCURA_BIN)
        if not obscura_path.exists():
            obscura_path = Path.cwd() / OBSCURA_BIN
        if not obscura_path.exists():
            logger.warning("Obscura binary not found: %s", OBSCURA_BIN)
            return False
        try:
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.Popen(
                [str(obscura_path), "serve", "--port", str(OBSCURA_PORT), "--stealth"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            return cls._wait_for_cdp(timeout=8)
        except Exception as e:
            logger.warning("Failed to start Obscura: %s", e)
            return False

    @classmethod
    def _cleanup_browsers(cls):
        """Disconnect CDP without killing any browser processes.
        The user's browser should NEVER be killed automatically."""
        if cls._cdp:
            cls._cdp.close()
            cls._cdp = None
        time.sleep(0.2)

    @classmethod
    def _is_port_in_use(cls, port: int) -> bool:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0

    @classmethod
    def _wait_for_cdp(cls, timeout: float = 8.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = requests.get(f"http://127.0.0.1:{OBSCURA_PORT}/json", timeout=0.5)
                if resp.ok:
                    return True
            except Exception:
                pass
            time.sleep(0.25)
        return False

    @classmethod
    def get_active_page_url(cls) -> str:
        cls._ensure_browser()
        try:
            return cls._cdp.evaluate("window.location.href")
        except:
            return ""

    @classmethod
    def get_active_page_url_safe(cls) -> str:
        try:
            return cls.get_active_page_url()
        except Exception:
            return ""

    @classmethod
    def click_at(cls, x: float, y: float):
        """Perform a mouse click at the specified x, y coordinates via CDP."""
        cls._ensure_browser()
        # Ensure we round to integers for CDP
        x, y = int(x), int(y)
        try:
            cls._cdp.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
            time.sleep(0.05)
            cls._cdp.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        except Exception as e:
            logger.warning(f"Failed to click at {x}, {y}: {e}")

    @classmethod
    def navigate(cls, url: str, wait: bool = True):
        cls._ensure_browser()
        logger.info(f"Navigating to {url}...")
        try:
            cls._cdp.send("Page.navigate", {"url": url})
        except Exception as e:
            logger.warning(f"Navigation failed: {e}. Attempting browser recovery...")
            cls.close() # Close stale connection
            cls._ensure_browser()
            cls._cdp.send("Page.navigate", {"url": url})
            
        if wait:
            cls.wait_for_ready(timeout=8)

    @classmethod
    def wait_for_ready(cls, timeout: float = 8.0) -> bool:
        cls._ensure_browser()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if cls._abort_execution:
                return False
            try:
                state = cls._cdp.evaluate("document.readyState")
                if state in ("interactive", "complete"):
                    return True
            except Exception:
                pass
            time.sleep(0.2)
        return False

    @classmethod
    def observe_active_page(cls) -> dict:
        # Don't force launch a browser just to observe background context
        cls._ensure_browser(force=False)
        if not cls._cdp or not cls._cdp.is_alive():
            return {}
        js = """
        () => {
          const isVisible = (el) => {
            const rect = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden";
          };
          const textOf = (el) => (
            el.innerText ||
            el.value ||
            el.getAttribute("aria-label") ||
            el.getAttribute("placeholder") ||
            el.getAttribute("name") ||
            el.getAttribute("title") ||
            ""
          ).trim().slice(0, 100);
          
          const elements = Array.from(document.querySelectorAll('a, button, input, textarea'))
            .filter(isVisible)
            .slice(0, 40)
            .map((el, i) => ({
              index: i,
              tag: el.tagName.toLowerCase(),
              text: textOf(el),
              ariaLabel: el.getAttribute("aria-label") || "",
              placeholder: el.getAttribute("placeholder") || "",
              role: el.getAttribute("role") || "",
              type: el.getAttribute("type") || "",
              bbox: el.getBoundingClientRect().toJSON()
            }));

          return {
            title: document.title,
            url: location.href,
            bodyText: (document.body.innerText || "").slice(0, 3000),
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
    def _run_dom_action(cls, action: str, labels: list[str] = None, value: str = "") -> str:
        cls._ensure_browser()
        url = cls.get_active_page_url_safe()
        remembered = cls._action_memory.recall(url, action, labels)
        for selector in remembered:
            result = cls._run_selector_action(action, selector, value)
            if not str(result).startswith("failed"):
                cls._record_action_event(url, action, "memory", labels or [], [selector], True)
                return result
            cls._action_memory.mark_failure(url, action, labels, selector)

        payload = json.dumps({
            "action": action,
            "labels": labels or [],
            "value": value,
        })
        js = f"""
        (() => {{
          const payload = {payload};
          const norm = (v) => (v || "").toString().trim().toLowerCase();
          const visible = (el) => {{
            const r = el.getBoundingClientRect();
            const s = getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
          }};
          const cssEscape = (value) => {{
            if (window.CSS && CSS.escape) return CSS.escape(value);
            return value.replace(/["\\\\#.;:[\\]>+~*^$|=\\s]/g, "\\\\$&");
          }};
          const quoteValue = (value) => value.replace(/["\\\\]/g, "\\\\$&");
          const selectorFor = (el) => {{
            const tag = el.tagName.toLowerCase();
            if (el.id) return "#" + cssEscape(el.id);
            for (const attr of ["aria-label", "placeholder", "name", "title"]) {{
              const value = el.getAttribute(attr);
              if (value) return `${{tag}}[${{attr}}="${{quoteValue(value)}}"]`;
            }}
            const parent = el.parentElement;
            if (!parent) return tag;
            const siblings = Array.from(parent.children).filter(child => child.tagName === el.tagName);
            const index = siblings.indexOf(el) + 1;
            return `${{tag}}:nth-of-type(${{Math.max(index, 1)}})`;
          }};
          const textOf = (el) => [
            el.innerText,
            el.value,
            el.getAttribute("aria-label"),
            el.getAttribute("placeholder"),
            el.getAttribute("name"),
            el.getAttribute("title"),
            el.getAttribute("role")
          ].filter(Boolean).join(" ");
          const candidates = Array.from(document.querySelectorAll(
            'input, textarea, [contenteditable="true"], button, a, [role="button"], [role="textbox"], [role="searchbox"]'
          )).filter(visible);
          const labels = payload.labels.map(norm).filter(Boolean);
          const score = (el) => {{
            const hay = norm(textOf(el));
            let s = 0;
            for (const label of labels) {{
              if (hay === label) s += 10;
              else if (hay.includes(label)) s += 6;
            }}
            const tag = el.tagName.toLowerCase();
            const role = norm(el.getAttribute("role"));
            const type = norm(el.getAttribute("type"));
            if (payload.action === "fill") {{
              if (tag === "textarea" || role === "textbox" || role === "searchbox" || el.isContentEditable) s += 4;
              if (tag === "input" && !["button", "submit", "checkbox", "radio"].includes(type)) s += 4;
            }}
            if (payload.action === "click" && (tag === "button" || tag === "a" || role === "button")) s += 3;
            return s;
          }};
          let target = candidates.map(el => [score(el), el]).sort((a, b) => b[0] - a[0])[0];
          if (!target || target[0] <= 0) {{
            if (payload.action === "fill") {{
              target = candidates.find(el => {{
                const tag = el.tagName.toLowerCase();
                const type = norm(el.getAttribute("type"));
                return tag === "textarea" || el.isContentEditable || el.getAttribute("role") === "textbox" ||
                  (tag === "input" && !["button", "submit", "checkbox", "radio"].includes(type));
              }});
            }} else {{
              target = candidates[0];
            }}
          }} else {{
            target = target[1];
          }}
          if (!target) return "failed:no-target";
          target.scrollIntoView({{block: "center", inline: "center"}});
          target.focus();
          if (payload.action === "fill") {{
            if (target.isContentEditable) {{
              target.textContent = payload.value;
              target.dispatchEvent(new InputEvent("input", {{bubbles: true, inputType: "insertText", data: payload.value}}));
            }} else {{
              target.value = payload.value;
              target.dispatchEvent(new Event("input", {{bubbles: true}}));
              target.dispatchEvent(new Event("change", {{bubbles: true}}));
            }}
          }} else {{
            target.click();
          }}
          return {{
            ok: true,
            selector: selectorFor(target),
            text: norm(textOf(target)).slice(0, 80)
          }};
        }})()
        """
        try:
            result = cls._cdp.evaluate(js)
            if isinstance(result, dict) and result.get("ok"):
                selector = result.get("selector", "")
                cls._action_memory.remember(url, action, labels, selector)
                cls._record_action_event(url, action, "semantic", labels or [], [selector], True)
                return f"{action}:{result.get('text', '')}"
            cls._record_action_event(url, action, "semantic", labels or [], [], False, "no-result")
            return "failed"
        except Exception as e:
            logger.debug(f"DOM action failed: {e}")
            cls._record_action_event(url, action, "semantic", labels or [], [], False, str(e))
            return "failed"

    @classmethod
    def _run_selector_action(cls, action: str, selector: str, value: str = "") -> str:
        cls._ensure_browser()
        if cls._verifier:
            cls._verifier.take_snapshot()

        payload = json.dumps({"action": action, "selector": selector, "value": value})
        js = f"""
        (() => {{
          const payload = {payload};
          const target = document.querySelector(payload.selector);
          if (!target) return "failed:no-target";
          const rect = target.getBoundingClientRect();
          const style = getComputedStyle(target);
          if (rect.width <= 0 || rect.height <= 0 || style.visibility === "hidden" || style.display === "none") {{
            return "failed:not-visible";
          }}
          target.scrollIntoView({{block: "center", inline: "center"}});
          target.focus();
          if (payload.action === "fill") {{
            if (target.isContentEditable) {{
              target.textContent = payload.value;
              target.dispatchEvent(new InputEvent("input", {{bubbles: true, inputType: "insertText", data: payload.value}}));
            }} else {{
              target.value = payload.value;
              target.dispatchEvent(new Event("input", {{bubbles: true}}));
              target.dispatchEvent(new Event("change", {{bubbles: true}}));
            }}
          }} else {{
            target.click();
          }}
          return payload.action + ":memory";
        }})()
        """
        try:
            result = cls._cdp.evaluate(js) or "failed"
            
            # If successful or "memory" result, verify if it actually did something
            if cls._verifier and not str(result).startswith("failed"):
                if not cls._verifier.verify_action(action):
                    logger.info(f"Action '{action}' didn't change state. Attempting forced recovery...")
                    # Recovery: Forced coordinates-based click
                    if action == "click":
                        js_coords = f"(() => {{ const el = document.querySelector('{selector}'); const r = el.getBoundingClientRect(); return {{x: r.left + r.width/2, y: r.top + r.height/2}}; }})()"
                        coords = cls._cdp.evaluate(js_coords)
                        if coords:
                            cls.click_at(coords['x'], coords['y'])
                            if cls._verifier.verify_action("forced_click"):
                                return "success:forced"
                    
                    # If forced click failed, try Autonomous Vision Recovery
                    return cls._autonomous_vision_recovery(action, selector, value)

            return result
        except Exception as e:
            logger.debug("Remembered selector failed: %s", e)
            return "failed"

    @classmethod
    def _autonomous_vision_recovery(cls, action: str, selector: str, value: str = "") -> str:
        """Uses local vision (Moondream) to diagnose why an action failed."""
        logger.info("Triggering Autonomous Vision Recovery...")
        try:
            screenshot_path = "data/screenshots/recovery.png"
            os.makedirs("data/screenshots", exist_ok=True)
            
            # Capture full screen via CDP
            screenshot_data = cls._cdp.send("Page.captureScreenshot")
            if screenshot_data and "data" in screenshot_data:
                with open(screenshot_path, "wb") as f:
                    import base64
                    f.write(base64.b64decode(screenshot_data["data"]))
            
            vision = get_vision_engine()
            prompt = f"I am an AI assistant trying to perform a '{action}' on the element '{selector}'. " \
                     f"The action failed verification. Looking at this screenshot, what is the correct button or input " \
                     f"I should click? Describe its text or appearance clearly."
            
            diagnosis = vision.analyze_screenshot(screenshot_path, prompt)
            logger.info(f"Vision Diagnosis: {diagnosis}")
            
            # Use the diagnosis to try one last semantic match
            if diagnosis and len(diagnosis) < 200:
                # Try to find an element matching the visual description
                result = cls.click_resilient(None, labels=[diagnosis])
                if not str(result).startswith("failed"):
                    return f"success:vision_recovery({diagnosis})"
            
            return "failed_vision_recovery"
        except Exception as e:
            logger.error(f"Vision recovery failed: {e}")
            return "failed_vision_recovery"

    @classmethod
    def _record_action_event(
        cls,
        url: str,
        action: str,
        strategy: str,
        labels: list[str],
        selectors: list[str],
        success: bool,
        error: str = "",
    ):
        try:
            title = cls._cdp.evaluate("document.title") if cls._cdp else ""
        except Exception:
            title = ""
        with cls._state_lock:
            cls._action_events.append({
            "url": url,
            "title": title,
            "action": action,
            "strategy": strategy,
            "labels": labels,
            "selectors": selectors,
            "success": success,
            "error": error,
        })

    @classmethod
    def click_resilient(cls, page: Any, labels: list[str] = None, **kwargs) -> str:
        cls._ensure_browser()
        dom_result = cls._run_dom_action("click", labels=labels)
        if not str(dom_result).startswith("failed"):
            return dom_result
        dom = cls.observe_active_page()
        elements = dom.get("elements", [])
        
        target = None
        for label in (labels or []):
            for el in elements:
                haystack = " ".join([
                    el.get("text", ""),
                    el.get("ariaLabel", ""),
                    el.get("placeholder", ""),
                ]).lower()
                if label.lower() in haystack:
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
        dom_result = cls._run_dom_action("fill", labels=labels, value=value)
        if not str(dom_result).startswith("failed"):
            return dom_result
        time.sleep(0.2)
        for char in value:
            cls._cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": char})
        return "filled"

    @classmethod
    def press_key(cls, key: str) -> str:
        cls._ensure_browser()
        key_map = {
            "Enter": 13,
            "Tab": 9,
            "Escape": 27,
            "Backspace": 8,
        }
        windows_code = key_map.get(key, 0)
        params = {"type": "keyDown", "key": key}
        if windows_code:
            params["windowsVirtualKeyCode"] = windows_code
        cls._cdp.send("Input.dispatchKeyEvent", params)
        params["type"] = "keyUp"
        cls._cdp.send("Input.dispatchKeyEvent", params)
        return f"pressed:{key}"

    @staticmethod
    def get_mouse_position() -> dict:
        return {"x": 0, "y": 0}

    @staticmethod
    def capture_screenshot(page: Any, label: str = "") -> str:
        return ""

    @classmethod
    def capture_full_screenshot(cls, path: str = "screenshot.png") -> str:
        from core.platform_utils import capture_screenshot as platform_capture
        if platform_capture(path):
            return path
        try:
            cls._ensure_browser()
            if cls._cdp:
                result = cls._cdp.send("Page.captureScreenshot")
                if result and "data" in result:
                    import base64
                    with open(path, "wb") as f:
                        f.write(base64.b64decode(result["data"]))
                    return path
        except Exception as e:
            logger.warning(f"CDP screenshot failed: {e}")
        return ""

    @classmethod
    def check_health(cls) -> tuple[bool, str]:
        """Verify if CDP is reachable without forcing a full launch."""
        if cls._cdp and cls._cdp.is_alive():
            return True, "CDP connection is active"
        try:
            resp = requests.get(f"http://127.0.0.1:{OBSCURA_PORT}/json/version", timeout=1)
            if resp.ok:
                return True, "Browser/Obscura is running"
        except:
            pass
        return False, "Browser is not running (Normal for startup)"

    @staticmethod
    def with_retry(fn: Callable, retries: int = 3, delay: float = 1.0):
        last_e = None
        for attempt in range(retries):
            try:
                return fn()
            except Exception as e:
                last_e = e
                if attempt < retries - 1:
                    logger.warning(f"Retry {attempt+1}/{retries} failed: {e}")
                    time.sleep(delay * (attempt + 1))
        logger.warning(f"All {retries} retries failed: {last_e}")
        return None
