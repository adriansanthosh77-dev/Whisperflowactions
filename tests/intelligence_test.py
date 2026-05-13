"""
Grand Intelligence Test: Fuzzy Matching + Teach Mode + Context Awareness
"""
import sys
import os
import json
import time

sys.path.append(os.getcwd())
from core.planner import Planner, teach_reflex, _load_learned_reflexes
from models.intent_schema import Context

planner = Planner()
ctx = Context()

PASS = 0
FAIL = 0

def check(label, cmd, expect_match=True, expect_intent=None):
    global PASS, FAIL
    results = list(planner.plan(cmd, ctx))
    matched = len(results) > 0
    intent_ok = True
    if expect_intent and matched:
        intent_ok = any(expect_intent in r.intent for r in results)
    
    if matched == expect_match and intent_ok:
        PASS += 1
        intent_str = results[0].intent if results else "none"
        print(f"  [PASS] {label:45} -> {intent_str}")
    else:
        FAIL += 1
        intent_str = results[0].intent if results else "none"
        print(f"  [FAIL] {label:45} -> {intent_str}")

# ============================================================
print("=" * 65)
print("PHASE 1: FUZZY MATCHING")
print("Testing typos, abbreviations, and near-misses")
print("-" * 65)

# Typos that should fuzzy-match to real reflexes
check("Typo: 'minimze' -> minimize",        "minimze")
check("Typo: 'maximise window' -> maximize", "maximise window")
check("Typo: 'volme up' -> volume up",      "volme up")
check("Typo: 'scrol down' -> scroll down",  "scrol down")
check("Typo: 'fulscreen' -> fullscreen",    "fulscreen")
check("Typo: 'relaod' -> reload",           "relaod")
check("Typo: 'bookmrks' -> bookmarks",      "bookmrks")
check("Typo: 'task manger' -> task manager", "task manger")
check("Typo: 'open noteapad' -> notepad",    "open noteapad")
check("Typo: 'check baterry' -> battery",    "check baterry")

# ============================================================
print("\n" + "=" * 65)
print("PHASE 2: TEACH MODE")
print("Teaching JARVIS brand new reflexes, then verifying them")
print("-" * 65)

# Teach JARVIS some custom reflexes
teach_reflex("open my portfolio", "launch_app", {"app": "chrome", "url": "https://myportfolio.com"})
teach_reflex("morning routine", "launch_app", {"app": "chrome", "url": "https://calendar.google.com"})
teach_reflex("check email", "launch_app", {"app": "chrome", "url": "https://gmail.com"})

# Verify they were saved
learned = _load_learned_reflexes()
saved_ok = "open my portfolio" in learned and "morning routine" in learned and "check email" in learned
if saved_ok:
    print(f"  [PASS] Saved 3 custom reflexes to disk.")
    PASS += 1
else:
    print(f"  [FAIL] Custom reflexes not saved properly.")
    FAIL += 1

# Now test that JARVIS recognizes them
check("Learned: 'open my portfolio'",  "open my portfolio")
check("Learned: 'morning routine'",    "morning routine")
check("Learned: 'check email'",        "check email")

# Test fuzzy matching ON learned reflexes
check("Fuzzy+Learned: 'check emal'",   "check emal")

# ============================================================
print("\n" + "=" * 65)
print("PHASE 3: CONTEXT AWARENESS")
print("Testing that reflexes adapt based on active page")
print("-" * 65)

# Test 1: Normal context (no URL) - play should be pc_action
ctx_normal = Context()
results_normal = list(planner.plan("play", ctx_normal))
if results_normal and results_normal[0].intent == "pc_action":
    print(f"  [PASS] 'play' on desktop -> pc_action (media key)")
    PASS += 1
else:
    print(f"  [FAIL] 'play' on desktop should be pc_action")
    FAIL += 1

# Test 2: YouTube context - play should become browser_action
ctx_yt = Context()
ctx_yt.dom = {"url": "https://www.youtube.com/watch?v=abc123"}
results_yt = list(planner.plan("play", ctx_yt))
if results_yt and results_yt[0].intent == "browser_action":
    print(f"  [PASS] 'play' on YouTube -> browser_action (click play)")
    PASS += 1
else:
    intent = results_yt[0].intent if results_yt else "none"
    print(f"  [FAIL] 'play' on YouTube should be browser_action, got {intent}")
    FAIL += 1

# Test 3: Netflix context - pause should become browser_action
ctx_nf = Context()
ctx_nf.dom = {"url": "https://www.netflix.com/watch/12345"}
results_nf = list(planner.plan("pause", ctx_nf))
if results_nf and results_nf[0].intent == "browser_action":
    print(f"  [PASS] 'pause' on Netflix -> browser_action (click pause)")
    PASS += 1
else:
    intent = results_nf[0].intent if results_nf else "none"
    print(f"  [FAIL] 'pause' on Netflix should be browser_action, got {intent}")
    FAIL += 1

# Test 4: Google Search context - scroll should become browser scroll
ctx_gs = Context()
ctx_gs.dom = {"url": "https://www.google.com/search?q=cats"}
results_gs = list(planner.plan("scroll down", ctx_gs))
if results_gs and results_gs[0].intent == "browser_action":
    print(f"  [PASS] 'scroll down' on Google Search -> browser_action")
    PASS += 1
else:
    intent = results_gs[0].intent if results_gs else "none"
    print(f"  [FAIL] 'scroll down' on Google should be browser_action, got {intent}")
    FAIL += 1

# ============================================================
print("\n" + "=" * 65)
print(f"GRAND TOTAL: {PASS}/{PASS+FAIL} Tests Passed.")
if FAIL == 0:
    print("PERFECT SCORE: All three intelligence systems are operational.")
else:
    print(f"Issues found: {FAIL} test(s) need attention.")
print("=" * 65)

# Cleanup test data
try:
    os.remove(os.path.join("data", "learned_reflexes.json"))
except:
    pass
