"""
TEACH MODE Integration Test
Tests both Manual Teaching and Auto-LLM Learning paths.
"""
import sys, os, time
sys.path.append(os.getcwd())

os.environ["OLLAMA_BASE_URL"] = "http://localhost:99999"  # Force offline
os.environ["OPENAI_API_KEY"] = ""

from core.planner import Planner
from core.teach_mode import get_teach_mode, TeachMode
from models.intent_schema import Context

planner = Planner()
ctx = Context()
tm = get_teach_mode()

PASS = 0
FAIL = 0

def check(label, success):
    global PASS, FAIL
    if success:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}")

print("=" * 65)
print("JARVIS TEACH MODE INTEGRATION TEST")
print("=" * 65)

# --- PHASE 1: Manual Teaching ---
print("\n[PHASE 1] MANUAL TEACHING (Record & Replay)")

# Start recording
results = list(planner.plan("record this", ctx))
check("Voice trigger: 'record this' recognized", 
      results and results[0].data.get("mode") == "teach")
check("TeachMode is now recording", tm.is_recording())

# Simulate recording some steps
tm.record_step("pc_action", "pc", {"operation": "launch_app", "app": "chrome", "url": "https://github.com"})
tm.record_step("browser_action", "browser", {"action": "click", "target": "new repository"})
tm.record_step("pc_action", "pc", {"operation": "type", "text": "my-new-project"})

# Stop recording
results = list(planner.plan("stop recording", ctx))
check("Voice trigger: 'stop recording' recognized",
      results and "3" in results[0].data.get("text", ""))

# Save as named workflow
tm.recorded_steps = [
    {"intent": "pc_action", "app": "pc", "data": {"operation": "launch_app", "app": "chrome", "url": "https://github.com"}},
    {"intent": "browser_action", "app": "browser", "data": {"action": "click", "target": "new repository"}},
    {"intent": "pc_action", "app": "pc", "data": {"operation": "type", "text": "my-new-project"}}
]
results = list(planner.plan("save as create github repo", ctx))
check("Voice trigger: 'save as create github repo' recognized",
      results and results[0].data.get("mode") == "teach_saved")

# Now replay it!
results = list(planner.plan("create github repo", ctx))
check(f"Replay workflow: got {len(results)} steps", len(results) == 3)
if results:
    check("Step 1 is launch chrome", results[0].data.get("operation") == "launch_app")
    check("Step 2 is click new repo", results[1].data.get("action") == "click")
    check("Step 3 is type project name", results[2].data.get("operation") == "type")

# --- PHASE 2: Auto-LLM Learning ---
print("\n[PHASE 2] AUTO-LLM LEARNING (Cache & Replay)")

# Simulate what happens after the LLM solves something
tm.save_llm_result("write a python script to sort a list", [
    {"intent": "pc_action", "app": "vscode", "target": "", "data": {"operation": "launch_app", "app": "vscode"}},
    {"intent": "pc_action", "app": "pc", "target": "", "data": {"operation": "type", "text": "sorted_list = sorted(my_list)"}}
])

# Now that same command should be INSTANT (no LLM needed)
results = list(planner.plan("write a python script to sort a list", ctx))
check("Auto-cached LLM result replays instantly", len(results) >= 2)
check("First step is launch vscode", results[0].app == "vscode" if results else False)

# Fuzzy match on cached LLM result
results = list(planner.plan("write a python script to sort a lst", ctx))
check("Fuzzy match on cached LLM result works", len(results) >= 2)

# --- PHASE 3: Workflow Stats ---
print("\n[PHASE 3] WORKFLOW MANAGEMENT")

results = list(planner.plan("what have you learned", ctx))
check("'what have you learned' lists workflows",
      results and "Learned workflows" in results[0].data.get("text", ""))

stats = tm.get_stats()
check(f"Stats: {stats['total_workflows']} workflows, {stats['manual_taught']} manual, {stats['llm_learned']} auto",
      stats["total_workflows"] >= 2)

# --- PHASE 4: Persistence ---
print("\n[PHASE 4] PERSISTENCE (survives restart)")

# Create a fresh TeachMode instance (simulates restart)
tm2 = TeachMode()
workflow = tm2.find_workflow("create github repo")
check("Manual workflow survives restart", workflow is not None)

workflow2 = tm2.find_workflow("write a python script to sort a list")
check("LLM-cached workflow survives restart", workflow2 is not None)

# Cleanup
try: os.remove(os.path.join("data", "learned_workflows.json"))
except: pass
try: os.remove(os.path.join("data", "learned_reflexes.json"))
except: pass

# --- FINAL SCORE ---
print("\n" + "=" * 65)
total = PASS + FAIL
print(f"FINAL SCORE: {PASS}/{total} Tests Passed.")
if FAIL == 0:
    print("PERFECT: Teach Mode is fully operational.")
else:
    print(f"{FAIL} test(s) need attention.")
print("=" * 65)
