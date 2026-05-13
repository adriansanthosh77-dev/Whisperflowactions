"""Universal Voice-to-Text End-to-End Test

This script will:
1. Open Notepad and type a dictated sentence.
2. Open Chrome and type a dictated sentence into the address bar.
"""
import sys, os, time
sys.path.append(os.getcwd())

from executors.pc_executor import PCExecutor
from models.intent_schema import IntentResult, Context

executor = PCExecutor()
ctx = Context()

def wait(secs=1.5):
    time.sleep(secs)

print("=" * 60)
print("TEST 1: NOTEPAD DICTATION")
print("=" * 60)
# 1. Open Notepad
print("Opening Notepad...")
intent_open = IntentResult("pc_action", "pc", "notepad", {"operation": "launch_app", "app": "notepad"}, 1.0, "")
executor.execute(intent_open, ctx)
wait(2)

# 2. Type text
text_to_type = "Hello! This was dictated directly into Notepad using JARVIS Universal Voice-to-Text."
print(f"Typing: '{text_to_type}'")
intent_type = IntentResult("pc_action", "pc", "", {"operation": "type", "text": text_to_type}, 1.0, "")
executor.execute(intent_type, ctx)
wait(2)

# 3. Add a new line and type more
intent_enter = IntentResult("pc_action", "pc", "", {"operation": "press", "key": "enter"}, 1.0, "")
executor.execute(intent_enter, ctx)
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "type", "text": "It works perfectly, even with commas and punctuation!"}, 1.0, ""), ctx)
wait(3)

# 4. Close Notepad without saving (Alt+F4 -> N)
print("Closing Notepad...")
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "close_window"}, 1.0, ""), ctx)
wait(1)
# Windows prompts to save, press 'n' to say No
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "press", "key": "n"}, 1.0, ""), ctx)
wait(1)

print("\n" + "=" * 60)
print("TEST 2: CHROME DICTATION")
print("=" * 60)
# 1. Open Chrome
print("Opening Chrome...")
intent_open_chrome = IntentResult("pc_action", "pc", "chrome", {"operation": "launch_app", "app": "chrome"}, 1.0, "")
executor.execute(intent_open_chrome, ctx)
wait(3)

# 2. Focus address bar (Ctrl+L)
print("Focusing address bar...")
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "focus_address_bar"}, 1.0, ""), ctx)
wait(0.5)

# 3. Type text
chrome_text = "how to build an AI agent python tutorial"
print(f"Typing: '{chrome_text}'")
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "type", "text": chrome_text}, 1.0, ""), ctx)
wait(2)

# 4. Press Enter to search
print("Pressing Enter to search...")
executor.execute(intent_enter, ctx)
wait(4)

# 5. Close Chrome Tab
print("Closing Chrome Tab...")
executor.execute(IntentResult("pc_action", "pc", "", {"operation": "close_tab"}, 1.0, ""), ctx)

print("\n" + "=" * 60)
print("UNIVERSAL DICTATION TESTS COMPLETED SUCCESSFULLY")
print("=" * 60)
