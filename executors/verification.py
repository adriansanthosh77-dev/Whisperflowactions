import time
import logging
from typing import Optional, Any

logger = logging.getLogger(__name__)

class VerificationEngine:
    """
    Ensures JARVIS actions actually result in state changes.
    Implements a simple "Before and After" comparison for URLs and DOM elements.
    """
    def __init__(self, cdp):
        self.cdp = cdp
        self.last_snapshot = None

    def take_snapshot(self) -> dict:
        """Captures the current URL and a hash of the visible interactive elements."""
        try:
            url = self.cdp.evaluate("window.location.href")
            # Simple hash-like representation of visible interactive elements
            elements_count = self.cdp.evaluate("document.querySelectorAll('a, button, input').length")
            dom_text = self.cdp.evaluate("document.body.innerText.slice(0, 500)")
            
            snapshot = {
                "url": url,
                "elements_count": elements_count,
                "text_hash": hash(dom_text),
                "ts": time.time()
            }
            self.last_snapshot = snapshot
            return snapshot
        except Exception:
            return {}

    def verify_action(self, action: str, timeout: float = 2.0) -> bool:
        """
        Polls the browser to see if the state has changed since the last snapshot.
        Returns True if a change is detected, False otherwise.
        """
        if not self.last_snapshot:
            return True # Nothing to compare against

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                current_url = self.cdp.evaluate("window.location.href")
                if current_url != self.last_snapshot["url"]:
                    logger.info(f"Action Verified: URL changed to {current_url}")
                    return True
                
                current_count = self.cdp.evaluate("document.querySelectorAll('a, button, input').length")
                if current_count != self.last_snapshot["elements_count"]:
                    logger.info(f"Action Verified: DOM structure changed (Element count: {current_count})")
                    return True
                
                # If we're filling a field, check if the value changed (optional/advanced)
                
            except Exception:
                pass
            time.sleep(0.2)
            
        logger.warning(f"Action Verification Failed: No state change detected after {action}")
        return False

    def check_goal_met(self, goal_description: str) -> bool:
        """
        Advanced: Use simple heuristics to check if a specific goal (e.g. 'Login') was met.
        """
        # Placeholder for future LLM or heuristic verification
        return True
