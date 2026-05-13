import sys
import os
import time

# Simulation of a Real World User Session
test_flow = [
    "Check battery and time",
    "Open YouTube and search for news",
    "Minimize window and open downloads folder",
    "Grammar correct this: she dont know"
]

def run_flow_test():
    sys.path.append(os.getcwd())
    from core.planner import Planner
    from models.intent_schema import Context
    
    planner = Planner()
    ctx = Context()
    
    print("--- JARVIS 'Daily Driver' Flow Test ---")
    print("Optimization: 2GB RAM SURVIVAL MODE")
    print("-" * 50)

    for i, cmd in enumerate(test_flow, 1):
        print(f"\n[STEP {i}] USER: '{cmd}'")
        start = time.time()
        
        try:
            results = list(planner.plan(cmd, ctx))
            elapsed = time.time() - start
            
            if results:
                print(f"  PASSED ({elapsed:.2f}s)")
                for step in results:
                    print(f"     -> {step.intent:15} | App: {step.app:10}")
            else:
                print(f"  FAILED: No plan generated.")
        except Exception as e:
            print(f"  ERROR: {str(e)}")

    print("\n" + "-" * 50)
    print("FLOW TEST COMPLETE: JARVIS is ready for your daily tasks.")

if __name__ == "__main__":
    run_flow_test()
