import time
import logging
import re
from executors.base_executor import BaseExecutor
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://calendar.google.com"

class CalendarExecutor(BaseExecutor):

    def read_events(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        try:
            self._ensure_browser()
            self.navigate(CALENDAR_URL)
            self.wait_for_ready(timeout=10)
            time.sleep(2)

            text = self._cdp.evaluate("document.body.innerText")[:5000]
            events = self._parse_events(text)
            if events:
                return True, f"Upcoming events:\n" + "\n".join(events[:8])
            return True, "No upcoming events found on your calendar."
        except Exception as e:
            return False, f"Calendar read failed: {str(e)[:80]}"

    def _parse_events(self, text: str) -> list[str]:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        events = []
        for line in lines:
            if re.match(r"^\d", line) and len(line) > 10:
                events.append(line)
        return events[:10]
