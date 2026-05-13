"""
STEALTH MODE AUDIT
Verifies that JARVIS can switch between Visual and Background (Stealth) modes
on demand, and that the Orchestrator correctly handles the visibility decision.
"""
# Mock dependencies that might fail in headless environments
import sys
from unittest.mock import MagicMock
sys.modules["sounddevice"] = MagicMock()
sys.modules["pynput"] = MagicMock()
sys.modules["pynput.keyboard"] = MagicMock()
sys.modules["websockets"] = MagicMock()
sys.modules["websockets.sync"] = MagicMock()
sys.modules["websockets.sync.client"] = MagicMock()
sys.modules["ui.overlay"] = MagicMock()
sys.modules["ui.overlay"].State = MagicMock()
sys.modules["ui.overlay"].run_overlay_in_thread = MagicMock()

import os
import time
sys.path.append(os.getcwd())

from core.planner import Planner
from core.orchestrator import JARVISOrchestrator
from executors.base_executor import BaseExecutor
from models.intent_schema import Context

# Mock the HUD and Voice for the test
class MockOverlay:
    def set_state(self, *args, **kwargs): pass
    def prompt_text(self, title=""): return "Stealth Mode" # Simulate user choosing Stealth
    def stop(self): pass
    def show_reflexes(self, *args): pass

class MockTTS:
    def say(self, *args, **kwargs): pass

print("=" * 80)
print("JARVIS STEALTH MODE AUDIT")
print("=" * 80)

orchestrator = JARVISOrchestrator()
orchestrator.overlay = MockOverlay()
orchestrator.tts = MockTTS()

# 1. Simulate a command with BROWSER_SELECTED flag
cmd = "research spaceX on perplexity BROWSER_SELECTED"
ctx = Context()

print(f"\n[Test 1] Triggering Visibility Prompt for: '{cmd}'")
os.environ["JARVIS_INTERACTIVE"] = "true"

# We call _execute_text which will call plan, see the flag, and trigger the decision handler
# In our mock, the handler will 'choose' Stealth Mode.
orchestrator._execute_text(cmd, ctx)

is_stealth = os.getenv("USE_OBSCURA", "false").lower() == "true"
if is_stealth:
    print("  [PASS] BaseExecutor.toggle_stealth_mode was called and set USE_OBSCURA=true.")
else:
    print("  [FAIL] USE_OBSCURA was not set to true after stealth selection.")

# 2. Simulate switching back to Visual
print("\n[Test 2] Switching back to Visual Mode...")
orchestrator.overlay.prompt_text = lambda title="": "Watch Jarvis"
orchestrator._execute_text(cmd, ctx)

is_stealth = os.getenv("USE_OBSCURA", "false").lower() == "true"
if not is_stealth:
    print("  [PASS] Visual mode successfully reset USE_OBSCURA=false.")
else:
    print("  [FAIL] USE_OBSCURA is still true after visual selection.")

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
orchestrator._shutdown()
