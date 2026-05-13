"""
Local Models Test for Brain Router
Verifies that specialized text categories can successfully route to local Ollama models,
and that Local Image Generation successfully attempts to hit Automatic1111 (Stable Diffusion).
"""
import sys, os
import requests
sys.path.append(os.getcwd())

# Ensure no API keys are present to test local fallback
os.environ["OPENAI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""

from core.brain_router import call_model, MODELS

original_post = requests.post
original_get = requests.get

class MockResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        pass

def mock_post(url, **kwargs):
    print(f"    -> Intercepted Request to: {url}")
    
    if "127.0.0.1:7860/sdapi/v1/txt2img" in url:
        return MockResponse({"images": ["base64_image_data_mock"]})
    elif "localhost:11434/api/chat" in url:
        return MockResponse({"message": {"content": "MOCK_LOCAL_OLLAMA_RESPONSE"}})
    
    return MockResponse({}, 400)

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

print("=" * 70)
print("TESTING LOCAL AI MODELS")
print("=" * 70)

tasks_to_test = [
    # (Task Prompt, Category, Provider, Expected Output)
    ("design an electrical board schematic", "engineering_cad", "ollama", "MOCK_LOCAL_OLLAMA_RESPONSE"),
    ("create a unity script for jumping", "game_development", "ollama", "MOCK_LOCAL_OLLAMA_RESPONSE"),
    ("automate this workflow", "automation_workflow", "ollama", "MOCK_LOCAL_OLLAMA_RESPONSE"),
    ("generate a photo of a dog", "image_generation", "local", "Local Image generated via Stable Diffusion! Check your SD output folder."),
]

PASS = 0
FAIL = 0

for prompt, category, provider, expected_output in tasks_to_test:
    print(f"\n[Prompt: '{prompt}'] -> {category.upper()} -> {provider.upper()}")
    
    # Force provider for testing
    MODELS[category]["provider"] = provider
    
    response = call_model(category, "System", prompt)
    
    if response == expected_output:
        print(f"  [PASS] Successfully routed locally to {provider.upper()} and parsed output.")
        PASS += 1
    else:
        print(f"  [FAIL] Output Mismatch! Got: {response}")
        FAIL += 1

print("\n" + "=" * 70)
print(f"FINAL SCORE: {PASS}/{len(tasks_to_test)} Local Workflows Verified.")
print("=" * 70)

requests.post = original_post
requests.get = original_get
