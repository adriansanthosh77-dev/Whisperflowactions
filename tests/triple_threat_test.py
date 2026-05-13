import sys
import os
import time

# Testing Triple-Compound Commands (2 PC + 1 Browser)
triple_threat_commands = [
    "Minimize this window, open my downloads, and search for cars on Google",
    "Mute the volume, open task manager, and open YouTube",
    "Snap this window left, open documents, and search Wikipedia for Space",
    "Close current tab, lock my PC, and open Amazon",
    "Volume up, open settings, and search maps for New York",
    "Fullscreen this window, open pictures folder, and open Netflix",
    "Reload the page, open cmd, and search for weather on Google",
    "Go back, open notepad, and search for stock prices on Yahoo",
    "Next tab, open calculator, and open Reddit",
    "Zoom in, open desktop folder, and search for news on Bing"
]

def test_triple_threat():
    sys.path.append(os.getcwd())
    from core.planner import Planner
    from models.intent_schema import Context
    
    planner = Planner()
    ctx = Context()
    
    print("--- JARVIS Triple-Threat Adaptability Test ---")
    print("Goal: 2 PC Reflexes + 1 Browser Reflex in 1 Prompt")
    print("-" * 65)

    passed = 0
    for i, cmd in enumerate(triple_threat_commands, 1):
        print(f"\n[TEST {i}] PROMPT: '{cmd}'")
        try:
            results = list(planner.plan(cmd, ctx))
            if len(results) >= 3:
                print(f"  PASSED: Generated {len(results)} steps.")
                for j, step in enumerate(results, 1):
                    print(f"     Step {j}: {step.intent:15} | App: {step.app:10}")
                passed += 1
            else:
                print(f"  FAILED: Only generated {len(results)} steps.")
        except Exception as e:
            print(f"  ERROR: {str(e)}")

    print("\n" + "-" * 65)
    print(f"FINAL SCORE: {passed}/{len(triple_threat_commands)} Triple-Tasks Succeeded.")

if __name__ == "__main__":
    test_triple_threat()
