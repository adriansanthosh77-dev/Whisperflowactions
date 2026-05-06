"""
context_collector.py — Captures runtime context for intent enrichment.

Grabs: active window title, active URL (if Chrome), selected text,
clipboard contents. All non-blocking with graceful fallbacks.
"""

import subprocess
import platform
import logging
import pyperclip
from models.intent_schema import Context
from executors.base_executor import BaseExecutor

logger = logging.getLogger(__name__)
OS = platform.system()  # "Darwin", "Linux", "Windows"


class ContextCollector:
    def collect(self) -> Context:
        return Context(
            active_app=self._get_active_app(),
            url=self._get_browser_url(),
            selected_text=self._get_selected_text(),
            clipboard=self._get_clipboard(),
            dom=BaseExecutor.observe_active_page(),
            mouse=BaseExecutor.get_mouse_position(),
        )

    def _get_active_app(self) -> str:
        try:
            if OS == "Darwin":
                script = 'tell application "System Events" to get name of first process whose frontmost is true'
                out = subprocess.check_output(["osascript", "-e", script], timeout=2)
                return out.decode().strip()
            elif OS == "Linux":
                out = subprocess.check_output(
                    ["xdotool", "getactivewindow", "getwindowname"], timeout=2
                )
                return out.decode().strip()
            elif OS == "Windows":
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return buf.value
        except Exception as e:
            logger.debug(f"get_active_app failed: {e}")
        return ""

    def _get_browser_url(self) -> str:
        """Get URL from Chrome/Chromium on macOS or Linux."""
        try:
            if OS == "Darwin":
                script = '''
                tell application "Google Chrome"
                    get URL of active tab of front window
                end tell
                '''
                out = subprocess.check_output(["osascript", "-e", script], timeout=2)
                return out.decode().strip()
            elif OS == "Linux":
                # xdotool + wmctrl approach for Chrome on Linux
                out = subprocess.check_output(
                    ["xdotool", "getactivewindow", "getwindowname"], timeout=2
                )
                title = out.decode().strip()
                # Extract URL pattern from window title if present
                if "http" in title:
                    parts = title.split("http")
                    return "http" + parts[-1].split(" ")[0]
        except Exception as e:
            logger.debug(f"get_browser_url failed: {e}")
        return ""

    def _get_selected_text(self) -> str:
        """
        Get selected text via clipboard trick:
        1. Save clipboard
        2. Simulate Cmd/Ctrl+C
        3. Read new clipboard
        4. Restore clipboard
        """
        try:
            original = pyperclip.paste()
            self._simulate_copy()
            import time; time.sleep(0.1)
            selected = pyperclip.paste()
            if selected != original:
                pyperclip.copy(original)
                return selected.strip()[:2000]  # cap at 2000 chars
        except Exception as e:
            logger.debug(f"get_selected_text failed: {e}")
        return ""

    def _simulate_copy(self):
        if OS == "Darwin":
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "c" using command down'],
                timeout=2
            )
        elif OS == "Linux":
            subprocess.run(["xdotool", "key", "ctrl+c"], timeout=2)
        elif OS == "Windows":
            import ctypes
            VK_CONTROL = 0x11
            VK_C = 0x43
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_C, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_C, 0, 2, 0)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)

    def _get_clipboard(self) -> str:
        try:
            return pyperclip.paste().strip()[:2000]
        except Exception:
            return ""
