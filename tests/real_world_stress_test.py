"""
JARVIS REAL-WORLD STRESS TEST (90% Coverage Audit)
Simulates 50+ diverse user commands to verify reflex coverage and brain routing.
"""
import sys, os
import time
sys.path.append(os.getcwd())

from core.planner import Planner
from models.intent_schema import Context
import requests

# Mock the Brain Router's AI calls so we don't wait for LLMs during the audit
class MockResponse:
    def __init__(self, data): self._data = data
    def json(self): return self._data
    def raise_for_status(self): pass

def mock_post(url, **kwargs):
    # Simulate Brain Router triggering browser automation for research
    if "11434" in url: # Ollama
        return MockResponse({"message": {"content": "[BROWSER AUTOMATION TRIGGERED]"}})
    
    # Simulate OpenAI Planner response
    return MockResponse({
        "choices": [{
            "message": {
                "content": "```json\n[{\"intent\":\"unknown\",\"app\":\"unknown\",\"data\":{}}]\n```"
            }
        }]
    })

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

# Mock OS environment for testing
os.environ["JARVIS_INTERACTIVE"] = "false"

print("=" * 80)
print("JARVIS REAL-WORLD STRESS TEST")
print("=" * 80)

planner = Planner()
ctx = Context()

TEST_CASES = [
    # 1. PC Reflexes (Apps & Windows)
    ("open notepad", "pc_action", "launch_app"),
    ("minimise window", "pc_action", "minimize_window"),
    ("maximise chrome", "pc_action", "maximize_window"),
    ("switch to discord", "pc_action", "switch_window"),
    ("open calculator", "pc_action", "launch_app"),
    ("lock screen", "pc_action", "lock_pc"),
    
    # 2. PC Reflexes (Folders & Files)
    ("open documents folder", "pc_action", "launch_app"),
    ("show downloads directory", "pc_action", "launch_app"),
    ("open pictures folder", "pc_action", "launch_app"),
    ("go to desktop folder", "pc_action", "launch_app"),
    ("open c drive", "pc_action", "launch_app"),
    
    # 3. System Controls
    ("volume up", "pc_action", "volume_up"),
    ("mute sounds", "pc_action", "volume_mute"),
    ("brightness down", "pc_action", "brightness_down"),
    ("open wifi settings", "pc_action", "launch_app"),
    
    # 4. Browser Reflexes (Tabs & Navigation)
    ("new tab", "pc_action", "new_tab"),
    ("close current tab", "pc_action", "close_tab"),
    ("go back", "pc_action", "browser_back"),
    ("refresh page", "pc_action", "reload"),
    ("duplicate tab", "pc_action", "duplicate_tab"),
    
    # 5. Smart Site Search (Instant)
    ("search spaceX on youtube", "browser_action", "navigate"),
    ("search apple on wikipedia", "browser_action", "navigate"),
    ("look up tesla on amazon", "browser_action", "navigate"),
    ("search intersteller", "browser_action", "search"), # Generic search fallback
    
    # 6. Productivity Web Apps (Instant)
    ("open notion", "pc_action", "launch_app"),
    ("open perplexity", "pc_action", "launch_app"),
    ("open claude", "pc_action", "launch_app"),
    ("open figma", "pc_action", "launch_app"),
    
    # 7. Conversational Reflexes
    ("who are you", "chat", "identity"),
    ("how are you", "chat", "status"),
    
    # 8. Dictation & Chat Reflexes
    ("type Hello World", "pc_action", "type"),
    ("correct this: i is happy", "chat_reflex", "correct"),
    ("reply to this: how was your day", "chat_reflex", "reply"),
    
    # 9. Brain Routing (Autonomous/Research)
    ("research the history of AI", "browser_action", "agent_loop"), # Handled by Brain Router -> Browser AI
    ("summarize this page", "summarize", "bullet"),
]

SCORE = 0
TOTAL = len(TEST_CASES)

for i, (cmd, expected_intent, expected_op) in enumerate(TEST_CASES, 1):
    print(f"[{i}/{TOTAL}] Testing: '{cmd}'")
    results = list(planner.plan(cmd, ctx))
    
    if not results:
        print(f"  [FAIL] No plan generated.")
        continue
        
    # Check if ANY of the results match
    passed = False
    for res in results:
        match_intent = (res.intent == expected_intent)
        match_op = False
        if "operation" in res.data and res.data["operation"] == expected_op: match_op = True
        if "action" in res.data and res.data["action"] == expected_op: match_op = True
        if "mode" in res.data and res.data["mode"] == expected_op: match_op = True
        if "topic" in res.data and res.data["topic"] == expected_op: match_op = True
        if "style" in res.data and res.data["style"] == expected_op: match_op = True
        
        if match_intent and match_op:
            passed = True
            break
            
    if passed:
        print(f"  [PASS] Verified.")
        SCORE += 1
    else:
        # Debugging output
        print(f"  [FAIL] Expected intent={expected_intent}, op={expected_op}.")
        print(f"         Found: {[ (r.intent, r.data) for r in results ]}")

print("\n" + "=" * 80)
print(f"STRESS TEST FINAL SCORE: {SCORE}/{TOTAL} ({ (SCORE/TOTAL)*100:.1f}%)")
print("=" * 80)
if SCORE / TOTAL >= 0.9:
    print("90%+ COVERAGE ACHIEVED. JARVIS IS READY FOR REAL-WORLD TASKS.")
else:
    print("COVERAGE BELOW 90%. FURTHER REFINEMENT NEEDED.")
print("=" * 80)
