"""
Multi-Modal Brain Router Providers Test
Mocks the API requests to verify that the router correctly constructs requests
for OpenAI (Image) and Replicate (Image/Video).
"""
import sys, os
import requests
sys.path.append(os.getcwd())

# Force environment variables for the test
os.environ["OPENAI_API_KEY"] = "sk-mock-openai-key"
os.environ["REPLICATE_API_TOKEN"] = "r8_mock_replicate_token"

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
    
    if "api.openai.com/v1/images/generations" in url:
        return MockResponse({"data": [{"url": "https://mock-openai-image.com/img.png"}]})
    elif "api.replicate.com" in url:
        return MockResponse({"urls": {"get": "https://api.replicate.com/v1/predictions/mock-id"}})
    
    return MockResponse({}, 400)

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

print("=" * 60)
print("TESTING MULTI-MODAL API PROVIDERS (MOCKED)")
print("=" * 60)

providers_to_test = [
    ("image_generation", "openai", "dall-e-3", "Image generated: https://mock-openai-image.com/img.png"),
    ("image_generation", "replicate", "stability-ai/sdxl", "Image generation started (Replicate): https://api.replicate.com/v1/predictions/mock-id"),
    ("video_generation", "replicate", "stability-ai/stable-video-diffusion", "Video generation started (Replicate): https://api.replicate.com/v1/predictions/mock-id"),
]

PASS = 0
FAIL = 0

for task_type, provider, model, expected in providers_to_test:
    print(f"\n[Testing {provider.upper()} ({model}) for {task_type.upper()}]")
    
    # Temporarily force the config
    if task_type not in MODELS:
        MODELS[task_type] = {}
    MODELS[task_type]["provider"] = provider
    MODELS[task_type]["model"] = model
    
    response = call_model(task_type, "Test System", "A beautiful painting of a futuristic city")
    
    if response == expected:
        print(f"  [PASS] Successfully routed and parsed {provider.upper()} multi-modal response.")
        PASS += 1
    else:
        print(f"  [FAIL] Expected '{expected}', got '{response}'")
        FAIL += 1

print("\n" + "=" * 60)
print(f"FINAL SCORE: {PASS}/{len(providers_to_test)} Multi-Modal Providers Tested Successfully.")
print("=" * 60)

requests.post = original_post
requests.get = original_get
