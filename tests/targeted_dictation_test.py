"""Targeted Dictation Test (Teach Mode + Type in App)"""
import sys, os
sys.path.append(os.getcwd())

from core.planner import Planner
from core.teach_mode import get_teach_mode
from models.intent_schema import Context

planner = Planner()
ctx = Context()
tm = get_teach_mode()

PASS = 0
FAIL = 0

def test_targeted_dictation(command, expected_intents):
    global PASS, FAIL
    print(f"\nCommand: '{command}'")
    results = list(planner.plan(command, ctx))
    
    intents = [r.intent for r in results]
    ops = [r.data.get("operation", r.data.get("action", "")) for r in results]
    
    print(f"  Generated sequence: {list(zip(intents, ops))}")
    
    if len(results) == expected_intents:
        print(f"  [PASS] Expected {expected_intents} steps, got {len(results)}")
        PASS += 1
    else:
        print(f"  [FAIL] Expected {expected_intents} steps, got {len(results)}")
        FAIL += 1

print("=" * 70)
print("TEST 1: Normal Dictation (No App specified)")
test_targeted_dictation("type hello world", 1)  # Just 1 step: type

print("\n" + "=" * 70)
print("TEST 2: Dictation in App (Untaught)")
# User says "in discord", but JARVIS doesn't know where the text box is.
# Should be 2 steps: 1. Launch/Switch Discord, 2. Type
test_targeted_dictation("type hello world in discord", 2)

print("\n" + "=" * 70)
print("TEST 3: Teaching the Focus Workflow")
# Simulate the user teaching JARVIS where the WhatsApp chat box is.
tm.start_recording()
tm.record_step("browser_action", "browser", {"action": "click", "target": "WhatsApp Chat Input"})
result = tm.stop_recording()
tm.save_manual_workflow("focus whatsapp", result["steps"])
print("  [SUCCESS] Taught JARVIS 'focus whatsapp'")

print("\n" + "=" * 70)
print("TEST 4: Dictation in App (Taught)")
# Verify it's actually in TeachMode
print("  Workflows in TeachMode:", [w["trigger"] for w in tm.list_workflows()])
print("  find_workflow result:", tm.find_workflow("focus whatsapp") is not None)

test_targeted_dictation("type I am running late in whatsapp", 3)

# Cleanup
try: os.remove(os.path.join("data", "learned_workflows.json"))
except: pass

print("\n" + "=" * 70)
print(f"FINAL SCORE: {PASS}/{PASS+FAIL} Tests Passed.")
print("=" * 70)
