"""Brain Router Test - Verify task classification and model routing."""
import sys, os
sys.path.append(os.getcwd())

from core.brain_router import detect_task_type, get_model_for_task, get_brain_status

PASS = 0
FAIL = 0

def check(label, command, expected_type):
    global PASS, FAIL
    detected = detect_task_type(command)
    if detected == expected_type:
        PASS += 1
        config = get_model_for_task(detected)
        print(f"  [PASS] {label:50} -> {detected:10} -> {config['provider']}/{config['model']}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label:50} -> got '{detected}', expected '{expected_type}'")

print("=" * 80)
print("JARVIS BRAIN ROUTER TEST")
print("=" * 80)

print("\n[CODING TASKS] -> Should route to Coding Brain")
check("'write a python sort function'",      "write a python sort function", "coding")
check("'debug this javascript code'",        "debug this javascript code", "coding")
check("'create a function to parse JSON'",   "create a function to parse JSON", "coding")
check("'fix this code error'",               "fix this code error", "coding")
check("'implement a binary search algorithm'","implement a binary search algorithm", "coding")

print("\n[CREATIVE TASKS] -> Should route to Creative Brain")
check("'write an email to my boss'",         "write an email to my boss", "creative")
check("'draft a professional message'",      "draft a professional message", "creative")
check("'compose a birthday poem'",           "compose a birthday poem", "creative")
check("'rewrite this in a formal tone'",     "rewrite this in a formal tone", "creative")

print("\n[ANALYSIS TASKS] -> Should route to Analysis Brain")
check("'summarize this article'",            "summarize this article", "analysis")
check("'explain quantum computing'",         "explain quantum computing", "analysis")
check("'analyze the pros and cons'",         "analyze the pros and cons", "analysis")
check("'compare React vs Vue'",             "compare React vs Vue", "analysis")

print("\n[RESEARCH TASKS] -> Should route to Research Brain")
check("'what is machine learning'",          "what is machine learning", "research")
check("'tell me about SpaceX'",             "tell me about SpaceX", "research")
check("'latest news on AI'",                "latest news on AI", "research")
check("'how does blockchain work'",          "how does blockchain work", "research")

print("\n[ACTION TASKS] -> Should route to General (handled by reflexes)")
check("'open youtube'",                      "open youtube", "general")
check("'minimize window'",                   "minimize window", "general")
check("'volume up'",                         "volume up", "general")

print("\n--- Current Brain Configuration ---")
status = get_brain_status()
for task_type, model in status.items():
    print(f"  {task_type:12} -> {model}")

print("\n" + "=" * 80)
total = PASS + FAIL
print(f"FINAL SCORE: {PASS}/{total} Tasks Correctly Classified.")
print("=" * 80)
