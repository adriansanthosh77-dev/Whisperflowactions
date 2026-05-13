"""
stress_test_jarvis.py — Autonomous Brain Stress Test

Simulates 10 diverse user commands and verifies the Planner's 
ability to generate correct, multi-step logic on the 1B model.
"""

import sys
import os
import json
import logging
from pathlib import Path

# Adjust path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.planner import Planner
from models.intent_schema import Context

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("stress-test")

TEST_CASES = [
    ("Open YouTube", "Reflex"),
    ("Search for cats", "Direct Search"),
    ("Open YouTube and search for lo-fi music", "Reflex -> Search Handoff"),
    ("Search for Vijay, download his photo, and paste it in games folder", "Complex Multi-Step"),
    ("Minimize this window", "PC Reflex"),
    ("What is on my screen?", "Vision Intent"),
    ("Open Notion and create a task for milk", "App Integration"),
    ("Grammar correct this: i is happy", "Chat Reflex"),
    ("Take a screenshot and open it", "Compound PC Action"),
    ("Launch calculator and type 5 plus 5", "App + Interaction")
]

def run_stress_test():
    planner = Planner()
    context = Context(url="", active_app="chrome", dom={})
    
    results = []
    logger.info("🚀 Starting 10-Point Brain Stress Test...")
    logger.info("-" * 50)

    for i, (command, category) in enumerate(TEST_CASES, 1):
        logger.info(f"Test #{i} [{category}]: '{command}'")
        
        try:
            steps = list(planner.plan(command, context))
            
            if not steps:
                logger.error("  ❌ FAILED: No steps generated.")
                results.append(False)
                continue
            
            # Validation logic
            success = True
            if category == "Reflex" and len(steps) != 1:
                logger.warning(f"  ⚠️ Note: Expected 1 step for reflex, got {len(steps)}")
            
            if category == "Complex Multi-Step" and len(steps) < 3:
                logger.error(f"  ❌ FAILED: Complex command only produced {len(steps)} steps.")
                success = False
            
            if category == "Vision Intent" and not any(s.intent == "describe_screen" for s in steps):
                logger.error("  ❌ FAILED: Vision command didn't trigger describe_screen.")
                success = False

            if success:
                logger.info(f"  ✅ PASSED: Generated {len(steps)} steps.")
                for s in steps:
                    logger.info(f"     -> {s.intent} ({s.app})")
            
            results.append(success)

        except Exception as e:
            logger.error(f"  ❌ CRASHED: {e}")
            results.append(False)
        
        logger.info("-" * 30)

    total_passed = sum(results)
    logger.info("-" * 50)
    logger.info(f"🏁 Final Result: {total_passed}/10 Passed.")
    
    if total_passed == 10:
        logger.info("🔥 JARVIS is Battle-Ready for the Masses.")
    else:
        logger.warning("🔨 JARVIS needs further tuning.")

if __name__ == "__main__":
    run_stress_test()
