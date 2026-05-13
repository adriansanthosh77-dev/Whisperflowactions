"""Dictation Mode Test"""
import sys, os
sys.path.append(os.getcwd())

from core.planner import Planner
from models.intent_schema import Context

planner = Planner()
ctx = Context()

def test_dictation(command):
    print(f"\nCommand: '{command}'")
    results = list(planner.plan(command, ctx))
    for i, r in enumerate(results):
        print(f"  Step {i+1}: [{r.intent}] -> {r.data.get('operation', r.data.get('action', ''))} | Text/Target: '{r.data.get('text', r.target)}'")

test_dictation("type hello world and welcome to jarvis")
test_dictation("dictate this is a long sentence, it has commas, and it has the word then in it.")
test_dictation("type out I am jarvis")
test_dictation("write an email to my boss") # Should still go to AI because 'write' is not in the bypass regex
test_dictation("type open youtube and search for cats") # Should literally type it!
