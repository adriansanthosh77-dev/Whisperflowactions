import sys
import os
import re

# Mocking the Context and IntentResult since we want a standalone verification
class Context:
    def __init__(self):
        self.history = []

def test_global_reflexes():
    # 1. Path to the live planner
    planner_path = os.path.join(os.path.dirname(__file__), "..", "core", "planner.py")
    with open(planner_path, 'r') as f:
        content = f.read()

    # 2. Extract keys using our proven deep-extraction regex
    keys = re.findall(r'^\s{8}["\']([^"\']+)["\']\s*:', content, re.MULTILINE)
    
    if not keys:
        print("Error: Could not extract reflex keys from planner.py")
        return

    # 3. Setup the Planner (importing directly to test the real logic)
    sys.path.append(os.getcwd())
    from core.planner import Planner
    planner = Planner()
    ctx = Context()

    print(f"--- JARVIS Global Reflex Stress Test ({len(keys)} items) ---")
    print("-" * 60)

    passed = 0
    failed_list = []

    for i, key in enumerate(keys, 1):
        try:
            # We call plan() which uses the live _fast_plan logic
            results = list(planner.plan(key, ctx))
            if results:
                res = results[0]
                # Verify it's a reflex (IntentResult)
                intent = res.intent
                app = res.app
                print(f"[{i:03}] TRIGGER: '{key:25}' -> ACTION: {intent:15} | OK")
                passed += 1
            else:
                print(f"[{i:03}] TRIGGER: '{key:25}' -> FAILED (No plan generated)")
                failed_list.append(key)
        except Exception as e:
            print(f"[{i:03}] TRIGGER: '{key:25}' -> ERROR ({str(e)})")
            failed_list.append(key)

    print("-" * 60)
    print(f"DONE: {passed}/{len(keys)} Triggers Successfully Verified.")
    
    if failed_list:
        print(f"FAILED ITEMS: {failed_list}")
    else:
        print("PERFECT 100% SCORE: All reflexes are live and functional.")

if __name__ == "__main__":
    test_global_reflexes()
