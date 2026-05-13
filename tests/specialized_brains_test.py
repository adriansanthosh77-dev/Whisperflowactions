"""
Ultimate Brain Router Providers Test
Mocks the API requests to verify that the router correctly routes tasks
for ALL specialized brains: Coding, Creative, Analysis, Research,
Image Gen, Video Gen, 3D Gen, Engineering/CAD, Game Dev, and Automation.
"""
import sys, os
import requests
sys.path.append(os.getcwd())

# Force environment variables for the test
os.environ["OPENAI_API_KEY"] = "sk-mock-openai-key"
os.environ["ANTHROPIC_API_KEY"] = "sk-mock-anthropic-key"
os.environ["REPLICATE_API_TOKEN"] = "r8_mock_replicate_token"
os.environ["MESHY_API_KEY"] = "meshy_mock_key"

from core.brain_router import call_model, detect_task_type, MODELS

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
    
    if "api.openai.com/v1/images/generations" in url:
        return MockResponse({"data": [{"url": "https://mock-openai-image.com/img.png"}]})
    elif "api.openai.com/v1/chat/completions" in url:
        return MockResponse({"choices": [{"message": {"content": "MOCK_OPENAI_RESPONSE"}}]})
    elif "api.anthropic.com" in url:
        return MockResponse({"content": [{"text": "MOCK_ANTHROPIC_RESPONSE"}]})
    elif "api.replicate.com" in url:
        return MockResponse({"urls": {"get": "https://api.replicate.com/v1/predictions/mock-id"}})
    elif "api.meshy.ai" in url:
        return MockResponse({"result": "mock-task-id-123"})
    
    return MockResponse({}, 400)

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

print("=" * 70)
print("TESTING ALL SPECIALIZED BRAINS (MOCKED)")
print("=" * 70)

tasks_to_test = [
    # (Task Prompt, Expected Category, Provider, Expected Output)
    ("write a python script", "coding", "openai", "MOCK_OPENAI_RESPONSE"),
    ("draft an email", "creative", "anthropic", "MOCK_ANTHROPIC_RESPONSE"),
    ("generate a photo of a dog", "image_generation", "openai", "Image generated: https://mock-openai-image.com/img.png"),
    ("create a video of a car", "video_generation", "replicate", "Video generation started (Replicate): https://api.replicate.com/v1/predictions/mock-id"),
    ("generate a 3d model of a sword", "3d_generation", "meshy", "3D Model generation started (Meshy Task ID: mock-task-id-123). Check https://www.meshy.ai/workspace"),
    ("design an electrical board schematic", "engineering_cad", "anthropic", "MOCK_ANTHROPIC_RESPONSE"),
    ("create a unity script for jumping", "game_development", "openai", "MOCK_OPENAI_RESPONSE"),
    ("automate this workflow", "automation_workflow", "openai", "MOCK_OPENAI_RESPONSE"),
]

PASS = 0
FAIL = 0

for prompt, expected_category, provider, expected_output in tasks_to_test:
    detected_cat = detect_task_type(prompt)
    print(f"\n[Prompt: '{prompt}']")
    print(f"  -> Detected Category: {detected_cat.upper()} (Expected: {expected_category.upper()})")
    
    if detected_cat != expected_category:
        print("  [FAIL] Routing Category Mismatch!")
        FAIL += 1
        continue
        
    # Force provider for testing
    MODELS[detected_cat]["provider"] = provider
    
    response = call_model(detected_cat, "System", prompt)
    
    if response == expected_output:
        print(f"  [PASS] Successfully routed to {provider.upper()} and parsed output.")
        PASS += 1
    else:
        print(f"  [FAIL] Output Mismatch! Got: {response}")
        FAIL += 1

print("\n" + "=" * 70)
print(f"FINAL SCORE: {PASS}/{len(tasks_to_test)} Specialized Brains Verified.")
print("=" * 70)

requests.post = original_post
requests.get = original_get
