"""
Interactive Mode & Anti-Bot Test
1. Verifies that JARVIS asks for a choice between Local, API, and Browser if Interactive mode is ON.
2. Verifies that the Browser Executor detects login/captcha screens.
"""
import sys, os
sys.path.append(os.getcwd())

# 1. Test Interactive Decision Mode
os.environ["JARVIS_INTERACTIVE"] = "true"
from core.planner import Planner
from models.intent_schema import Context

planner = Planner()
ctx = Context()

print("=" * 70)
print("TESTING INTERACTIVE DECISION MODE")
print("=" * 70)
command = "write a professional email to my boss"
results = list(planner.plan(command, ctx))

if results and results[0].data.get("mode") == "decision_prompt":
    print(f"[PASS] JARVIS prompted for choice: {results[0].data['text']}")
    print(f"       Options provided: {results[0].data['options']}")
else:
    print("[FAIL] JARVIS did not prompt for decision.")

# 2. Test Anti-Bot Detection
print("\n" + "=" * 70)
print("TESTING ANTI-BOT / LOGIN DETECTION")
print("=" * 70)

from executors.browser_executor import BrowserExecutor
executor = BrowserExecutor()

# Mock the _cdp.evaluate to simulate a Login screen
class MockCDP:
    def evaluate(self, js):
        if "login" in js or "document.body.innerText" in js:
            return "login"
        return None

executor._cdp = MockCDP()
executor._browser_launched = True # Simulate browser is open
executor._ensure_browser = lambda: None # Bypass real browser connection

blocked, message = executor.check_for_blocking_elements()

if blocked:
    print(f"[PASS] JARVIS detected blocking screen: {message}")
else:
    print("[FAIL] JARVIS failed to detect blocking screen.")

print("=" * 70)
