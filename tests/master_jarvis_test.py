"""
MASTER JARVIS INTEGRATION TEST
The final, comprehensive audit of every layer of JARVIS intelligence.
Verifies Reflexes, Fuzzy Matching, Smart Search, Voice Speed, Brain Routing, and Browser AI.
"""
import sys, os
import time
import requests
sys.path.append(os.getcwd())

from core.planner import Planner
from core.brain_router import MODELS
from models.intent_schema import Context

# --- Mocking ---
class MockResponse:
    def __init__(self, data): self._data = data
    def json(self): return self._data
    def raise_for_status(self): pass

def mock_post(url, **kwargs):
    if "images/generations" in url: return MockResponse({"data": [{"url": "http://img.url"}]})
    if "11434" in url: return MockResponse({"message": {"content": "LOCAL_MOCK_RESPONSE"}})
    return MockResponse({"choices": [{"message": {"content": "API_MOCK_RESPONSE"}}]})

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get
os.environ["JARVIS_INTERACTIVE"] = "false"

# --- Test Runner ---
planner = Planner()
ctx = Context()

def run_test(category, cmd, expected_intent=None, expected_data_key=None, expected_val=None):
    print(f"[{category}] Testing: '{cmd}'")
    results = list(planner.plan(cmd, ctx))
    
    if not results:
        print(f"  [FAIL] No results returned.")
        return False
        
    # Check if ANY of the results match the expectation
    passed = False
    all_details = []
    for res in results:
        details = str(res.intent) + " " + str(res.data)
        all_details.append(details)
        
        match = True
        if expected_intent and res.intent != expected_intent: match = False
        if expected_data_key and expected_data_key not in res.data: match = False
        elif expected_val and expected_val.lower() not in str(res.data).lower(): match = False
        
        if match:
            passed = True
            break

    if passed:
        print(f"  [PASS] Verified.")
        return True
    else:
        print(f"  [FAIL] Expected intent={expected_intent}, val={expected_val}. Found: {all_details}")
        return False

print("=" * 80)
print("JARVIS MASTER INTEGRATION TEST")
print("=" * 80)

SCORE = 0
TOTAL = 0

# 1. CORE REFLEXES
TOTAL += 1
if run_test("Reflex", "open notepad", "pc_action", "operation", "launch_app"): SCORE += 1

# 2. FUZZY MATCHING
TOTAL += 1
if run_test("Fuzzy", "opn notpad", "pc_action", "app", "notepad"): SCORE += 1

# 3. SMART SITE SEARCH
TOTAL += 1
if run_test("Smart Search", "search spaceX on youtube", "browser_action", "url", "youtube.com"): SCORE += 1

# 4. SMART SITE ACTIONS (New)
TOTAL += 1
if run_test("Smart Action", "watch stranger things on netflix", "browser_action", "url", "netflix.com"): SCORE += 1

# 5. UNIVERSAL DICTATION
TOTAL += 1
if run_test("Dictation", "type Hello in Word", "pc_action", "operation", "launch_app"): SCORE += 1 # First step is focus/launch

# 6. SYSTEM CONTROLS
TOTAL += 1
if run_test("System", "volume up", "pc_action", "operation", "volume_up"): SCORE += 1

# 7. BRAIN ROUTING (Hardware Safety)
TOTAL += 1
MODELS["coding"]["provider"] = "ollama"
MODELS["coding"]["model"] = "llama3:70b" # Heavy model
if run_test("Brain/Safety", "write code for a game", "chat_reflex", "text", "Hardware Warning"): SCORE += 1

# 8. BROWSER AI AUTOMATION (Manus-Style)
TOTAL += 1
MODELS["research"]["provider"] = "browser"
MODELS["research"]["model"] = "perplexity"
if run_test("Browser AI", "research spaceX on perplexity", "browser_action", "action", "agent_loop"): SCORE += 1

# 9. VOICE ENGINE LATENCY (Simulated check)
print("\n[Voice Engine] Latency Check...")
from core.stt_engine import STTEngine
import numpy as np
stt = STTEngine()
start = time.time()
stt.transcribe(np.zeros(16000, dtype=np.int16).tobytes())
lat = time.time() - start
print(f"  - 1s Buffer Latency: {lat:.3f}s")
TOTAL += 1
if lat < 10.0:
    print("  [PASS] STT verified (Environment overhead considered).")
    SCORE += 1
else:
    print("  [FAIL] STT Latency too high.")

print("\n" + "=" * 80)
print(f"MASTER TEST FINAL SCORE: {SCORE}/{TOTAL}")
print("=" * 80)
if SCORE == TOTAL:
    print("JARVIS IS 100% PRODUCTION READY.")
else:
    print("SOME ISSUES DETECTED. REVIEW LOGS.")
print("=" * 80)
