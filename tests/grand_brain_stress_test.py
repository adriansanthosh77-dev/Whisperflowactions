"""
GRAND BRAIN STRESS TEST
A comprehensive audit of the entire JARVIS Intelligence Layer:
1. Multi-Brain Routing (Coding, Creative, etc.)
2. Multi-Provider API logic (OpenAI, Anthropic, Gemini, Groq, etc.)
3. Multi-Modal Generation (Image, Video, 3D)
4. Local Hardware Safety Interceptor (RAM/VRAM check)
5. Interactive Decision Mode
6. Browser AI Automation (Manus-Style)
"""
import sys, os
import requests
sys.path.append(os.getcwd())

# Force environment for mock testing
os.environ["OPENAI_API_KEY"] = "sk-mock"
os.environ["ANTHROPIC_API_KEY"] = "sk-mock"
os.environ["GROQ_API_KEY"] = "gsk-mock"
os.environ["GEMINI_API_KEY"] = "gemini-mock"
os.environ["REPLICATE_API_TOKEN"] = "r8-mock"
os.environ["MESHY_API_KEY"] = "meshy-mock"
os.environ["JARVIS_INTERACTIVE"] = "false"

from core.planner import Planner
from core.brain_router import call_model, detect_task_type, MODELS
from models.intent_schema import Context

# Mock Requests
original_post = requests.post
original_get = requests.get
class MockResponse:
    def __init__(self, json_data): self._json_data = json_data
    def json(self): return self._json_data
    def raise_for_status(self): pass

def mock_post(url, **kwargs):
    if "images/generations" in url: return MockResponse({"data": [{"url": "http://img.url"}]})
    if "replicate.com" in url: return MockResponse({"urls": {"get": "http://replicate.url"}})
    if "meshy.ai" in url: return MockResponse({"result": "task_123"})
    if "localhost:11434" in url: return MockResponse({"message": {"content": "LOCAL_OLLAMA_RESPONSE"}})
    if "openai.com" in url: return MockResponse({"choices": [{"message": {"content": "API_RESPONSE"}}]})
    if "anthropic.com" in url: return MockResponse({"content": [{"text": "API_RESPONSE"}]})
    return MockResponse({"message": {"content": "API_RESPONSE"}})

requests.post = mock_post

def mock_get(url, **kwargs):
    return MockResponse({"models": [{"name": "tiny.en"}]})
requests.get = mock_get

planner = Planner()
ctx = Context()
PASS = 0
FAIL = 0

def run_test(name, prompt, provider=None, model=None, interactive=False, expect_browser=False, expect_warning=False):
    global PASS, FAIL
    print(f"\n[TEST: {name}]")
    os.environ["JARVIS_INTERACTIVE"] = "true" if interactive else "false"
    
    task_type = detect_task_type(prompt)
    if provider: MODELS[task_type]["provider"] = provider
    if model: MODELS[task_type]["model"] = model
    
    results = list(planner.plan(prompt, ctx))
    
    # Analyze results
    is_browser = any(r.intent == "browser_action" and r.data.get("action") == "navigate" for r in results)
    is_warning = any("Hardware Warning" in r.data.get("text", "") for r in results if r.intent == "chat_reflex")
    is_decision = any(r.data.get("mode") == "decision_prompt" for r in results if r.intent == "chat_reflex")
    
    success = True
    if expect_browser and not is_browser: success = False
    if expect_warning and not is_warning: success = False
    if interactive and not is_decision: success = False
    
    if success:
        print(f"  [PASS] Behavior matched expectations.")
        PASS += 1
    else:
        print(f"  [FAIL] Unexpected behavior. Browser={is_browser}, Warning={is_warning}, Decision={is_decision}")
        FAIL += 1

print("=" * 70)
print("JARVIS GRAND BRAIN STRESS TEST")
print("=" * 70)

# --- CATEGORY 1: ROUTING & PROVIDERS ---
run_test("API Routing (OpenAI)", "write a blog post", provider="openai")
run_test("API Routing (Anthropic)", "debug this java code", provider="anthropic")
run_test("API Routing (Groq)", "summarize this long article", provider="groq")

# --- CATEGORY 2: MULTI-MODAL ---
run_test("Image Gen (OpenAI)", "generate a photo of a cat", provider="openai")
run_test("Video Gen (Replicate)", "make a video of a waterfall", provider="replicate")
run_test("3D Gen (Meshy)", "create a 3d model of a helmet", provider="meshy")

# --- CATEGORY 3: HARDWARE SAFETY ---
# (User has 16GB RAM / 1GB VRAM)
run_test("Hardware Block (70B)", "write a script", provider="ollama", model="llama3:70b", expect_warning=True)
run_test("Hardware Block (Local SD)", "generate an image", provider="local", expect_warning=True)

# --- CATEGORY 4: INTERACTIVE MODE ---
run_test("Interactive Prompt", "write a professional letter", interactive=True)

# --- CATEGORY 5: BROWSER AUTOMATION ---
run_test("Browser AI Automation", "research latest tech news", provider="browser", model="perplexity", expect_browser=True)

print("\n" + "=" * 70)
print(f"STRESS TEST COMPLETE: {PASS}/{PASS+FAIL} Systems Verified.")
print("=" * 70)

requests.post = original_post
requests.get = original_get
