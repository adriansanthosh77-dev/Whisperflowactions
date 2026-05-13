"""Physical End-to-End Targeted Dictation Test

This test simulates the user teaching JARVIS to click on Notepad to focus it,
and then uses the 'type X in Y' command to execute it physically.
"""
import sys, os, time
sys.path.append(os.getcwd())

from core.planner import Planner
from core.teach_mode import get_teach_mode
from executors.pc_executor import PCExecutor
from models.intent_schema import Context, IntentResult

planner = Planner()
ctx = Context()
tm = get_teach_mode()
executor = PCExecutor()

def wait(secs=1.5):
    time.sleep(secs)

print("=" * 60)
print("JARVIS SMART TARGETED DICTATION TEST")
print("=" * 60)

# --- 1. Preparation ---
# We teach JARVIS the "focus notepad" workflow.
# Normally the user would click the screen, but we simulate the record step here.
print("\n[TEACHING JARVIS]")
tm.start_recording()
# We don't have a physical click in PCExecutor right now, but launching Notepad auto-focuses it anyway.
# We'll record a dummy step just to prove the Teach Mode sequence is pulled correctly.
tm.record_step("pc_action", "pc", {"operation": "launch_app", "app": "notepad"})
result = tm.stop_recording()
tm.save_manual_workflow("focus notepad", result["steps"])
print(" -> Successfully taught 'focus notepad' to JARVIS")

# --- 2. Execution ---
print("\n[EXECUTING COMMAND]")
command = "type Hello! JARVIS automatically switched to Notepad and typed this. in notepad"
print(f"User says: '{command}'")

# Generate the plan exactly as JARVIS would
results = list(planner.plan(command, ctx))

print("\n[PLAN GENERATED]")
for i, r in enumerate(results):
    print(f"  Step {i+1}: [{r.intent}] -> {r.data.get('operation', r.data.get('action', ''))}")

print("\n[PHYSICAL EXECUTION]")
for r in results:
    if r.intent == "pc_action":
        executor.execute(r, ctx)
        wait(1)

# --- 3. Clean up ---
print("\n[CLEANUP]")
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "close_window"}, 1.0, ""), ctx)
wait(1)
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "press", "key": "n"}, 1.0, ""), ctx)

# Remove the test workflow so we don't pollute the user's data
try: os.remove(os.path.join("data", "learned_workflows.json"))
except: pass

print("\n" + "=" * 60)
print("TEST COMPLETED. You should have seen Notepad open and text appear.")
print("=" * 60)
