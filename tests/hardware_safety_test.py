"""
Hardware Checker Test
Verifies that JARVIS correctly detects system hardware (RAM/VRAM)
and intercepts heavy local model requests if the system is underpowered.
"""
import sys, os
import requests
sys.path.append(os.getcwd())

from core.brain_router import call_model, MODELS

# Ensure no API keys are present to test local fallback
os.environ["OPENAI_API_KEY"] = ""

original_post = requests.post
original_get = requests.get

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code
    def json(self): return self._json_data
    def raise_for_status(self): pass

def mock_post(url, **kwargs):
    return MockResponse({"message": {"content": "MOCK_SUCCESS"}})

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

print("=" * 70)
print("TESTING HARDWARE SAFETY CHECKER")
print("=" * 70)

tests = [
    # (Task Prompt, Category, Provider, Model, Expected to be Blocked?)
    ("write a python script", "coding", "ollama", "llama3:70b", True),       # 70B needs 32GB RAM
    ("design an electrical board", "engineering_cad", "ollama", "qwen:32b", True),  # 32B needs 24GB RAM
    ("write a python script", "coding", "ollama", "llama3:8b", False),       # 8B is fine on 16GB RAM
    ("generate a photo of a dog", "image_generation", "local", "stable-diffusion", True), # SD needs 4GB VRAM
]

PASS = 0
FAIL = 0

for prompt, category, provider, model, expected_blocked in tests:
    print(f"\n[Request: {model} via {provider.upper()}]")
    
    # Force provider and model for testing
    MODELS[category]["provider"] = provider
    MODELS[category]["model"] = model
    
    response = call_model(category, "System", prompt)
    
    was_blocked = response and "Hardware Warning" in response
    
    if was_blocked:
        print(f"  -> JARVIS INTERCEPTED: {response}")
    else:
        print("  -> JARVIS ALLOWED EXECUTION.")
        
    if was_blocked == expected_blocked:
        print("  [PASS] Expected behavior matched.")
        PASS += 1
    else:
        print(f"  [FAIL] Expected Blocked={expected_blocked}, but got Blocked={was_blocked}")
        FAIL += 1

print("\n" + "=" * 70)
print(f"FINAL SCORE: {PASS}/{len(tests)} Hardware Safety Checks Verified.")
print("=" * 70)

requests.post = original_post
requests.get = original_get
