"""
Autonomous Browser AI Test (Manus-Style)
Verifies that Browser AI Automation now uses an 'Agent Loop' 
instead of just hardcoded steps. This allows JARVIS to dynamically 
interact with the AI's UI.
"""
import sys, os
sys.path.append(os.getcwd())

from core.planner import Planner
from core.brain_router import MODELS
from models.intent_schema import Context

planner = Planner()
ctx = Context()

print("=" * 70)
print("TESTING AUTONOMOUS BROWSER AI (MANUS-STYLE)")
print("=" * 70)

# 1. Setup: Use Browser-based HuggingFace Chat
MODELS["research"]["provider"] = "browser"
MODELS["research"]["model"] = "huggingface"

command = "what are the top 3 open source models today"
print(f"Command: '{command}'")

results = list(planner.plan(command, ctx))

print("\nGenerated Sequence:")
for i, r in enumerate(results):
    op = r.data.get("operation", r.data.get("action", ""))
    goal = r.data.get("goal", "")
    target = r.target if r.target else ""
    print(f"  Step {i+1}: [{r.intent}] {op} {target} {goal}")

# 2. Validation
if any(r.data.get("action") == "agent_loop" for r in results):
    print("\n[PASS] JARVIS triggered the Autonomous Agent Loop for Browser AI.")
    print("       He will now dynamically find the chat box and send the message.")
else:
    print("\n[FAIL] JARVIS used hardcoded steps instead of the Agent Loop.")
    
print("=" * 70)
