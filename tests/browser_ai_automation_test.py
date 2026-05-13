"""
Browser AI Automation Multi-Step Test
Verifies that high-level tasks routed to 'browser' providers are expanded
into physical multi-step browser automation sequences (Navigate -> Wait -> Type -> Enter).
"""
import sys, os
sys.path.append(os.getcwd())

from core.planner import Planner
from core.brain_router import MODELS
from models.intent_schema import Context

planner = Planner()
ctx = Context()

print("=" * 70)
print("TESTING BROWSER AI AUTOMATION (MULTI-STEP)")
print("=" * 70)

# 1. Setup: Use Browser-based Perplexity for Research
MODELS["research"]["provider"] = "browser"
MODELS["research"]["model"] = "perplexity"

command = "research the latest news on spaceX"
print(f"Command: '{command}'")

results = list(planner.plan(command, ctx))

print("\nGenerated Sequence:")
for i, r in enumerate(results):
    op = r.data.get("operation", r.data.get("action", ""))
    target = r.target if r.target else ""
    print(f"  Step {i+1}: [{r.intent}] {op} {target}")

# 2. Validation
expected_steps = 4
if len(results) == expected_steps:
    print(f"\n[PASS] Successfully expanded high-level task into {expected_steps} physical steps.")
    
    # Check for specific steps
    if results[0].data.get("action") == "navigate" and "perplexity.ai" in results[0].data.get("url"):
        print("  [PASS] Step 1 is Navigate to Perplexity.")
    if results[2].data.get("operation") == "type" and command in results[2].data.get("text"):
        print("  [PASS] Step 3 is Type the prompt.")
else:
    print(f"\n[FAIL] Expected {expected_steps} steps, got {len(results)}.")
    
print("=" * 70)
