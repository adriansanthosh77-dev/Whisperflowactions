import time
import logging
import threading
import ctypes
from typing import List, Dict, Callable

logger = logging.getLogger(__name__)

class OverwatchRule:
    def __init__(self, pattern: str, action_label: str, callback: Callable):
        self.pattern = pattern.lower()
        self.action_label = action_label
        self.callback = callback
        self.last_triggered = 0

class ProactiveOverwatch:
    """
    Background monitor that watches window titles and suggests actions.
    Designed for zero-latency impact using native Win32 calls.
    """
    def __init__(self, trigger_callback: Callable):
        self.trigger_callback = trigger_callback
        self.rules: List[OverwatchRule] = []
        self._stop_signal = False
        self._last_title = ""
        
        # Default Rules
        self.add_rule("checkout", "Payment Assistance", self._default_action)
        self.add_rule("payment", "Payment Assistance", self._default_action)
        self.add_rule("stack overflow", "Code Explanation", self._default_action)
        self.add_rule("zoom", "Meeting Assistant", self._default_action)
        self.add_rule("github", "Repo Manager", self._default_action)

    def add_rule(self, pattern: str, action_label: str, callback: Callable):
        self.rules.append(OverwatchRule(pattern, action_label, callback))

    def _default_action(self, title: str, label: str):
        self.trigger_callback(title, label)

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()
        logger.info("Proactive Overwatch started.")

    def stop(self):
        self._stop_signal = True

    def _get_active_window_title(self) -> str:
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0: return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except:
            return ""

    def _loop(self):
        while not self._stop_signal:
            title = self._get_active_window_title()
            if title and title != self._last_title:
                self._last_title = title
                lower_title = title.lower()
                
                for rule in self.rules:
                    if rule.pattern in lower_title:
                        # Throttling: Don't trigger same rule within 60 seconds
                        if time.time() - rule.last_triggered > 60:
                            logger.info(f"Overwatch Trigger: '{rule.pattern}' matched '{title}'")
                            rule.last_triggered = time.time()
                            rule.callback(title, rule.action_label)
            
            time.sleep(2.0) # Low frequency polling to save battery/CPU

_OVERWATCH = None

def start_overwatch(callback: Callable):
    global _OVERWATCH
    if _OVERWATCH is None:
        _OVERWATCH = ProactiveOverwatch(callback)
        _OVERWATCH.start()
    return _OVERWATCH
