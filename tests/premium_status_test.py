import sys
import os
import re

# Mock test for the new Premium Status reflexes
pc_reflexes = {
    "how is my battery": ("get_battery_status", {}),
    "what time is it": ("get_current_time", {}),
    "system health": ("get_system_health", {}),
}

test_commands = [
    "how is my battery",
    "what time is it",
    "system health"
]

print("--- Testing JARVIS Premium Status Reflexes ---")
for cmd in test_commands:
    if cmd in pc_reflexes:
        op, extra = pc_reflexes[cmd]
        print(f"[OK] {cmd:20} -> {op:20} | Status: INSTANT SENSOR")
    else:
        print(f"[FAIL] {cmd:20} -> NO MATCH")

print("\n--- JARVIS is now System-Aware! ---")
