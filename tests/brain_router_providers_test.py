"""
Brain Router Multi-Provider Test
Mocks the API requests to verify that the router correctly constructs requests
for Gemini, Groq, Anthropic, OpenAI, and Ollama without requiring actual API keys.
"""
import sys, os
import requests
sys.path.append(os.getcwd())

# Force environment variables for the test
os.environ["OPENAI_API_KEY"] = "sk-mock-openai-key"
os.environ["ANTHROPIC_API_KEY"] = "sk-ant-mock-key"
os.environ["GROQ_API_KEY"] = "gsk_mock_groq_key"
os.environ["GEMINI_API_KEY"] = "AIzaSyMockGeminiKey"

from core.brain_router import call_model, MODELS

# We will monkeypatch requests.post to intercept the API calls
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
    
    if "api.openai.com" in url:
        return MockResponse({"choices": [{"message": {"content": "MOCK_OPENAI_RESPONSE"}}]})
    elif "api.anthropic.com" in url:
        return MockResponse({"content": [{"text": "MOCK_ANTHROPIC_RESPONSE"}]})
    elif "api.groq.com" in url:
        return MockResponse({"choices": [{"message": {"content": "MOCK_GROQ_RESPONSE"}}]})
    elif "generativelanguage.googleapis.com" in url:
        return MockResponse({"candidates": [{"content": {"parts": [{"text": "MOCK_GEMINI_RESPONSE"}]}}]})
    elif "localhost" in url:
        return MockResponse({"message": {"content": "MOCK_OLLAMA_RESPONSE"}})
    
    return MockResponse({}, 400)

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

print("=" * 60)
print("TESTING ALL API PROVIDERS (MOCKED)")
print("=" * 60)

providers_to_test = [
    ("coding", "openai", "gpt-4o", "MOCK_OPENAI_RESPONSE"),
    ("creative", "anthropic", "claude-3-5-sonnet", "MOCK_ANTHROPIC_RESPONSE"),
    ("analysis", "groq", "llama3-70b-8192", "MOCK_GROQ_RESPONSE"),
    ("research", "gemini", "gemini-1.5-pro", "MOCK_GEMINI_RESPONSE"),
    ("general", "ollama", "llama3", "MOCK_OLLAMA_RESPONSE")
]

PASS = 0
FAIL = 0

for task_type, provider, model, expected in providers_to_test:
    print(f"\n[Testing {provider.upper()} ({model}) for {task_type.upper()}]")
    
    # Temporarily force the config
    MODELS[task_type]["provider"] = provider
    MODELS[task_type]["model"] = model
    
    response = call_model(task_type, "Test System", "Test User")
    
    if response == expected:
        print(f"  [PASS] Successfully routed and parsed {provider.upper()} response.")
        PASS += 1
    else:
        print(f"  [FAIL] Expected '{expected}', got '{response}'")
        FAIL += 1

print("\n" + "=" * 60)
print(f"FINAL SCORE: {PASS}/{len(providers_to_test)} Providers Tested Successfully.")
print("=" * 60)

# Restore original post
requests.post = original_post
requests.get = original_get
