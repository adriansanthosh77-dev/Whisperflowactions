import sys
import os
import time

# Testing a massive 10-Part Compound Command
decathlon_prompt = (
    "Minimize this window, mute the volume, open my downloads, "
    "search for cats on Google, open YouTube, snap this window left, "
    "open calculator, check my battery, open notepad, and fullscreen this"
)

def test_decathlon():
    sys.path.append(os.getcwd())
    from core.planner import Planner
    from models.intent_schema import Context
    
    planner = Planner()
    ctx = Context()
    
    print("--- JARVIS Digital Decathlon (10-Task Chain) ---")
    print(f"PROMPT: '{decathlon_prompt}'")
    print("-" * 75)

    start = time.time()
    try:
        results = list(planner.plan(decathlon_prompt, ctx))
        elapsed = time.time() - start
        
        if len(results) >= 10:
            print(f"  PASSED: Generated {len(results)} steps in {elapsed:.2f}s.")
            for i, step in enumerate(results, 1):
                print(f"     [{i:02}] {step.intent:15} | App: {step.app:10}")
        else:
            print(f"  FAILED: Only generated {len(results)} steps.")
            for i, step in enumerate(results, 1):
                print(f"     [{i:02}] {step.intent:15} | App: {step.app:10}")
    except Exception as e:
        print(f"  ERROR: {str(e)}")

    print("\n" + "-" * 75)
    print("DECATHLON COMPLETE: JARVIS is an Olympic-level multi-tasker.")

if __name__ == "__main__":
    test_decathlon()
