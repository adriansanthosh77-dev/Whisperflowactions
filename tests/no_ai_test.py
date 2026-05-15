"""
NO-AI Test: Prove JARVIS works perfectly without any LLM.
Simulates Ollama being completely offline.
"""
import sys, os, time
sys.path.append(os.getcwd())

# Force AI offline by pointing to a dead endpoint
os.environ["OLLAMA_BASE_URL"] = "http://localhost:99999"
os.environ["LLM_PROVIDER"] = "ollama"
os.environ["OPENAI_API_KEY"] = ""

from core.planner import Planner, teach_reflex
from models.intent_schema import Context

planner = Planner()
ctx = Context()

PASS = 0
FAIL = 0

def test(label, cmd, expect_intent=None):
    global PASS, FAIL
    start = time.time()
    results = list(planner.plan(cmd, ctx))
    elapsed = time.time() - start
    
    if results and results[0].intent != "unknown":
        matched_intent = results[0].intent
        if expect_intent and expect_intent not in matched_intent:
            FAIL += 1
            print(f"  [FAIL] {label:50} -> {matched_intent} (expected {expect_intent}) [{elapsed:.3f}s]")
        else:
            PASS += 1
            print(f"  [PASS] {label:50} -> {matched_intent} [{elapsed:.3f}s]")
    else:
        FAIL += 1
        print(f"  [FAIL] {label:50} -> NO MATCH [{elapsed:.3f}s]")

print("=" * 70)
print("JARVIS NO-AI INDEPENDENCE TEST")
print("Ollama: OFFLINE | OpenAI: OFFLINE | Pure Python Brain: ACTIVE")
print("=" * 70)

# --- PHASE 1: Exact Reflexes (should be instant) ---
print("\n[PHASE 1] EXACT REFLEXES (201 hardcoded)")
test("Exact: 'minimize'",             "minimize",         "pc_action")
test("Exact: 'open youtube'",         "open youtube",     "pc_action")
test("Exact: 'search wikipedia'",     "search wikipedia", "browser_action")
test("Exact: 'volume up'",            "volume up",        "pc_action")
test("Exact: 'check battery'",        "check battery",    "pc_action")
test("Exact: 'open steam'",           "open steam",       "pc_action")
test("Exact: 'disk cleanup'",         "disk cleanup",     "pc_action")

# --- PHASE 2: Fuzzy Matching (typos) ---
print("\n[PHASE 2] FUZZY MATCHING (typos and near-misses)")
test("Fuzzy: 'minimze'",              "minimze",          "pc_action")
test("Fuzzy: 'voume up'",             "voume up",         "pc_action")
test("Fuzzy: 'open yotube'",          "open yotube",      "pc_action")
test("Fuzzy: 'task manger'",          "task manger",      "pc_action")
test("Fuzzy: 'scrll down'",           "scrll down",       "pc_action")

# --- PHASE 3: Smart Fallback (unknown but parseable) ---
print("\n[PHASE 3] SMART FALLBACK (no reflex, no AI, pure regex)")
test("Fallback: 'open spotify.com'",  "open spotify.com", "open_app")
test("Fallback: 'search for puppies'","search for puppies","browser_action")
test("Fallback: 'google best laptops'","google best laptops","browser_action")
test("Fallback: 'click the login button'", "click the login button", "browser_action")
test("Fallback: 'type hello world'",  "type hello world", "pc_action")
test("Fallback: 'go to reddit.com'",  "go to reddit.com", "open_app")

# --- PHASE 4: Multi-Step (Split & Conquer, no AI) ---
print("\n[PHASE 4] MULTI-STEP COMMANDS (Split & Conquer, no AI)")
cmd = "minimize, volume up, and open youtube"
results = list(planner.plan(cmd, ctx))
if len(results) >= 3:
    PASS += 1
    print(f"  [PASS] 3-step chain: {len(results)} steps generated")
else:
    FAIL += 1
    print(f"  [FAIL] 3-step chain: only {len(results)} steps")

cmd = "open calculator, mute, search for cats, and open downloads"
results = list(planner.plan(cmd, ctx))
if len(results) >= 4:
    PASS += 1
    print(f"  [PASS] 4-step chain: {len(results)} steps generated")
else:
    FAIL += 1
    print(f"  [FAIL] 4-step chain: only {len(results)} steps")

# --- PHASE 5: Teach Mode ---
print("\n[PHASE 5] TEACH MODE (learn new reflexes, no AI)")
teach_reflex("good morning", "launch_app", {"app": "chrome", "url": "https://calendar.google.com"})
test("Taught: 'good morning'",        "good morning",     "pc_action")
test("Fuzzy+Taught: 'good mornng'",   "good mornng",      "pc_action")

# Cleanup
try: os.remove(os.path.join("data", "learned_reflexes.json"))
except: pass

# --- FINAL SCORE ---
print("\n" + "=" * 70)
total = PASS + FAIL
print(f"FINAL SCORE: {PASS}/{total} Tests Passed.")
if FAIL == 0:
    print("PERFECT: JARVIS works 100% without any AI model running.")
else:
    print(f"{FAIL} test(s) need attention.")
print("=" * 70)
