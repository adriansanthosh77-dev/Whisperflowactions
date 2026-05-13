"""
ULTIMATE JARVIS INTELLIGENCE AUDIT
Validates all 10 major systems implemented during the intelligence upgrade phase.
"""
import sys, os
sys.path.append(os.getcwd())

os.environ["OLLAMA_BASE_URL"] = "http://localhost:99999"  # Force LLM offline for pure logic tests
os.environ["OPENAI_API_KEY"] = ""

from core.planner import Planner
from core.teach_mode import get_teach_mode
from core.brain_router import detect_task_type, get_model_for_task
from models.intent_schema import Context

planner = Planner()
ctx = Context()
tm = get_teach_mode()

PASS = 0
FAIL = 0

def check(label, success, info=""):
    global PASS, FAIL
    if success:
        PASS += 1
        print(f"  [PASS] {label:40} {info}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label:40} {info}")

print("=" * 70)
print("ULTIMATE JARVIS INTELLIGENCE AUDIT")
print("=" * 70)

# --- 1. EXACT REFLEXES ---
print("\n[1. EXACT REFLEXES]")
r = list(planner.plan("minimize window", ctx))
check("Exact PC Action", r and r[0].intent == "pc_action" and "minimize" in r[0].data.get("operation", ""))
r = list(planner.plan("search wikipedia", ctx))
check("Exact Browser Action", r and r[0].intent == "browser_action" and "search" in r[0].data.get("action", ""))

# --- 2. FUZZY MATCHING ---
print("\n[2. FUZZY MATCHING]")
r = list(planner.plan("minimze wndow", ctx))
check("Typo Auto-correct (PC)", r and r[0].intent == "pc_action" and "minimize" in r[0].data.get("operation", ""))
r = list(planner.plan("task manger", ctx))
check("Typo Auto-correct (System)", r and r[0].intent == "pc_action" and "task_manager" in r[0].data.get("operation", ""))

# --- 3. SMART FALLBACKS ---
print("\n[3. SMART FALLBACKS (No AI needed)]")
r = list(planner.plan("open spotify.com", ctx))
check("Regex App Launch", r and r[0].data.get("operation") == "launch_app")
r = list(planner.plan("google cute puppies", ctx))
check("Regex Browser Search", r and r[0].intent == "browser_action" and r[0].data.get("query") == "cute puppies")

# --- 4. MULTI-TASK SPLITTER ---
print("\n[4. MULTI-TASK SPLITTER]")
r = list(planner.plan("minimize window, volume up, and open youtube", ctx))
check("Split 3 commands correctly", len(r) == 3)

# --- 5. CONTEXT AWARENESS ---
print("\n[5. CONTEXT AWARENESS]")
ctx_desktop = Context()
r_desktop = list(planner.plan("play", ctx_desktop))
check("Desktop 'play' -> Media Key", r_desktop and r_desktop[0].intent == "pc_action")

ctx_yt = Context()
ctx_yt.dom = {"url": "https://www.youtube.com/watch?v=123"}
r_yt = list(planner.plan("play", ctx_yt))
check("YouTube 'play' -> Browser Click", r_yt and r_yt[0].intent == "browser_action")

# --- 6. TEACH MODE (MANUAL) ---
print("\n[6. TEACH MODE (MANUAL)]")
tm.start_recording()
tm.record_step("pc_action", "pc", {"operation": "launch_app", "app": "spotify"})
tm.record_step("pc_action", "pc", {"operation": "press", "key": "space"})
result = tm.stop_recording()
tm.save_manual_workflow("play music", result["steps"])
r = list(planner.plan("play music", ctx))
check("Replay Taught Workflow", len(r) == 2 and r[0].data.get("app") == "spotify")

# --- 7. TEACH MODE (AUTO-LLM) ---
print("\n[7. TEACH MODE (AUTO-LLM)]")
tm.save_llm_result("generate monthly report", [
    {"intent": "pc_action", "app": "excel", "data": {"operation": "launch_app", "app": "excel"}}
])
r = list(planner.plan("generate monthly report", ctx))
check("Replay Auto-Cached LLM Result", len(r) == 1 and r[0].data.get("app") == "excel")

# --- 8. BRAIN ROUTER ---
print("\n[8. BRAIN ROUTER]")
t1 = detect_task_type("write a python script")
check("Coding Task Routing", t1 == "coding", f"-> {get_model_for_task(t1)['label']}")
t2 = detect_task_type("draft an email to the client")
check("Creative Task Routing", t2 == "creative", f"-> {get_model_for_task(t2)['label']}")
t3 = detect_task_type("summarize this article")
check("Analysis Task Routing", t3 == "analysis", f"-> {get_model_for_task(t3)['label']}")
t4 = detect_task_type("open youtube")
check("Action Task Routing", t4 == "general", f"-> Handled by Reflexes")

# --- 9. UNIVERSAL DICTATION OVERRIDE ---
print("\n[9. UNIVERSAL DICTATION OVERRIDE]")
r = list(planner.plan("type hello world and welcome to jarvis", ctx))
check("Bypass Splitter for Dictation", len(r) == 1 and r[0].data.get("operation") == "type")

# --- 10. TARGETED DICTATION (APP FOCUS) ---
print("\n[10. TARGETED DICTATION]")
tm.start_recording()
tm.record_step("browser_action", "browser", {"action": "click", "target": "Discord Chat Box"})
res = tm.stop_recording()
tm.save_manual_workflow("focus discord", res["steps"])

r = list(planner.plan("type I am online in discord", ctx))
check("Switch App + Focus Click + Type", len(r) == 3, f"-> {[step.intent for step in r]}")

# Cleanup
try: os.remove(os.path.join("data", "learned_workflows.json"))
except: pass
try: os.remove(os.path.join("data", "learned_reflexes.json"))
except: pass

print("\n" + "=" * 70)
print(f"GRAND TOTAL: {PASS}/{PASS+FAIL} Tests Passed.")
if FAIL == 0:
    print("STATUS: PERFECT (10/10 Systems Operational)")
print("=" * 70)
