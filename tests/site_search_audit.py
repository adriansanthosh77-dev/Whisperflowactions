"""
SMART SITE SEARCH AUDIT
Verifies that JARVIS can handle 'Search X on Y' commands 
by constructing direct search URLs for popular platforms.
"""
import sys, os
sys.path.append(os.getcwd())

from core.planner import Planner
from models.intent_schema import Context

planner = Planner()
ctx = Context()

print("=" * 70)
print("JARVIS SMART SITE SEARCH AUDIT")
print("=" * 70)

test_cases = [
    ("search spiderman on youtube", "youtube.com/results"),
    ("search laptop on amazon", "amazon.com/s"),
    ("search python on github", "github.com/search"),
    ("search world war 2 on wikipedia", "wikipedia.org/wiki"),
    ("search funny cat on reddit", "reddit.com/search"),
    ("search latest news on google", "google.com/search")
]

SCORE = 0
for cmd, expected_url_part in test_cases:
    print(f"\nTesting: '{cmd}'")
    results = list(planner.plan(cmd, ctx))
    
    url = results[0].target if results else ""
    if expected_url_part in url:
        print(f"  [PASS] Target URL: {url}")
        SCORE += 1
    else:
        print(f"  [FAIL] Expected '{expected_url_part}' in target URL. Found: '{url}'")

print("\n" + "=" * 70)
print(f"SITE SEARCH SCORE: {SCORE}/{len(test_cases)} VERIFIED.")
print("=" * 80)
