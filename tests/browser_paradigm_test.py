"""
Ultimate Catalogue Test
Verifies the massive list of options and the new BROWSER automation paradigm.
"""
import sys, os
sys.path.append(os.getcwd())

from core.brain_router import list_available_options, call_model, MODELS

print(list_available_options())

print("\n" + "=" * 70)
print("TESTING BROWSER AUTOMATION PARADIGM")
print("=" * 70)

MODELS["research"]["provider"] = "browser"
MODELS["research"]["model"] = "perplexity"

response = call_model("research", "System", "who is the president")

if "[BROWSER AUTOMATION TRIGGERED]" in response:
    print(f"\n[PASS] Browser Triggered: {response}")
else:
    print(f"\n[FAIL] Expected Browser Trigger, got: {response}")
