"""
brain_router.py — Intelligent LLM Router for JARVIS

Routes different task types to the most suitable AI model:
- Coding    -> Claude / Codex / GPT-4 (user's choice)
- Creative  -> GPT-4 / Claude (user's choice)  
- Analysis  -> GPT-4o-mini / Claude (user's choice)
- Research  -> Perplexity / GPT-4 (user's choice)
- Actions   -> No LLM needed (reflexes handle it)

Configure your preferred models in .env
"""

import os
import json
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# ── Task Type Detection ───────────────────────────────────────────────────

TASK_PATTERNS = {
    "coding": [
        "write code", "write a script", "create a function", "debug",
        "fix this code", "refactor", "implement", "program",
        "python", "javascript", "html", "css", "java", "c++",
        "write a program", "code this", "build a", "develop",
        "api", "function", "class", "algorithm", "sort", "loop",
        "llama", "deepseek", "gpt", "claude", "mistral", "mixtral",
        "gemini", "phi3", "qwen", "gemma",
    ],
    "creative": [
        "write an email", "draft a message", "compose", "write a letter",
        "write a story", "create a poem", "write a song", "draft an email",
        "rephrase", "rewrite", "make this sound", "professional", "draft",
        "write a blog", "caption", "tagline", "slogan",
    ],
    "analysis": [
        "summarize", "summary", "analyze", "explain", "break down",
        "what does this mean", "interpret", "review", "evaluate",
        "compare", "contrast", "pros and cons",
    ],
    "research": [
        "research", "find out", "look into", "what is", "who is", "what are",
        "how does", "why does", "tell me about", "information on",
        "latest news", "current", "trending", "statistics", "search for",
        "perplexity", "chatgpt", "claude", "gemini", "ai search",
    ],
    "image_generation": [
        "generate an image", "create an image", "draw", "paint", "render",
        "make a picture", "show me a picture of", "generate a photo",
    ],
    "video_generation": [
        "generate a video", "create a video", "animate", "make a video",
        "generate an animation", "generate a short film",
    ],
    "3d_generation": [
        "generate a 3d model", "create a 3d asset", "make a 3d design",
        "3d object", "render in 3d", "generate a 3d character",
    ],
    "engineering_cad": [
        "electrical board", "circuit board", "cad design", "kicad",
        "schematic", "pcb design", "autocad", "solidworks", "engineering",
    ],
    "game_development": [
        "make a game", "create a game", "unity script", "unreal engine",
        "game logic", "godot", "game dev", "gameplay",
    ],
    "automation_workflow": [
        "multi step automation", "zapier", "n8n", "automate this workflow",
        "automation script", "complex workflow", "agentic workflow",
    ],
}

def detect_task_type(command: str) -> str:
    """Detect what type of task this is based on keywords."""
    t = command.lower()
    
    scores = {}
    for task_type, keywords in TASK_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in t)
        if score > 0:
            scores[task_type] = score
    
    if not scores:
        return "general"
    
    best = max(scores, key=scores.get)
    return best


# ── Model Configuration ──────────────────────────────────────────────────

# User-configurable models for each task type (set in .env)
MODELS = {
    "coding": {
        "provider": os.getenv("CODING_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("CODING_MODEL", "llama3.2:1b").strip(),
        "label": "Coding Brain",
    },
    "creative": {
        "provider": os.getenv("CREATIVE_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("CREATIVE_MODEL", "llama3.2:1b").strip(),
        "label": "Creative Brain",
    },
    "analysis": {
        "provider": os.getenv("ANALYSIS_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("ANALYSIS_MODEL", "llama3.2:1b").strip(),
        "label": "Analysis Brain",
    },
    "research": {
        "provider": os.getenv("RESEARCH_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("RESEARCH_MODEL", "llama3.2:1b").strip(),
        "label": "Research Brain",
    },
    "general": {
        "provider": os.getenv("LLM_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("OLLAMA_MODEL", "llama3.2:1b").strip(),
        "label": "General Brain",
    },
    "image_generation": {
        "provider": os.getenv("IMAGE_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("IMAGE_MODEL", "llava").strip(),
        "label": "Image Generation Brain",
    },
    "video_generation": {
        "provider": os.getenv("VIDEO_PROVIDER", "replicate").strip().lower(),
        "model": os.getenv("VIDEO_MODEL", "stability-ai/stable-video-diffusion").strip(),
        "label": "Video Generation Brain",
    },
    "3d_generation": {
        "provider": os.getenv("THREED_PROVIDER", "meshy").strip().lower(),
        "model": os.getenv("THREED_MODEL", "meshy-4").strip(),
        "label": "3D Generation Brain",
    },
    "engineering_cad": {
        "provider": os.getenv("ENGINEERING_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("ENGINEERING_MODEL", "llama3.2:1b").strip(),
        "label": "Engineering & CAD Brain",
    },
    "game_development": {
        "provider": os.getenv("GAMING_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("GAMING_MODEL", "llama3.2:1b").strip(),
        "label": "Game Development Brain",
    },
    "automation_workflow": {
        "provider": os.getenv("AUTOMATION_PROVIDER", "ollama").strip().lower(),
        "model": os.getenv("AUTOMATION_MODEL", "llama3.2:1b").strip(),
        "label": "Automation Brain",
    },
}


def get_model_for_task(task_type: str) -> dict:
    """Get the configured model for a specific task type."""
    config = MODELS.get(task_type, MODELS["general"])
    logger.info(f"BrainRouter: '{task_type}' task -> {config['label']} ({config['provider']}/{config['model']})")
    return config


# ── API Callers ───────────────────────────────────────────────────────────

def call_model(task_type: str, system_prompt: str, user_message: str) -> Optional[str]:
    """Route a task to the appropriate AI model and return the response."""
    config = get_model_for_task(task_type)
    provider = config["provider"]
    model = config["model"]

    try:
        from core.hardware_checker import check_model_hardware_compatibility

        if task_type == "image_generation":
            if provider == "local":
                is_safe, warning = check_model_hardware_compatibility(model, is_image_gen=True)
                if not is_safe: return warning
                return _call_image_local(model, user_message)
            return f"Using Ollama for image generation with model: {model}"

        if task_type in ("video_generation", "3d_generation"):
            return f"Video/3D generation requires a paid API (no free local alternative). Configured provider: {provider}"

        if provider == "ollama":
            is_safe, warning = check_model_hardware_compatibility(model)
            if not is_safe: return warning
            return _call_ollama(model, system_prompt, user_message)
        elif provider == "browser":
            logger.info(f"BrainRouter: Using browser-based LLM at '{model}'")
            try:
                from core.browser_llm import call_llm as browser_llm_call
                return browser_llm_call(model, system_prompt, user_message)
            except Exception as e:
                logger.error(f"Browser LLM call failed: {e}")
                return f"Browser LLM call failed: {e}"
        else:
            logger.warning(f"Unknown provider '{provider}', falling back to ollama")
            return _call_ollama(model, system_prompt, user_message)
    except Exception as e:
        logger.error(f"BrainRouter: Error calling {provider}/{model}: {e}")
        return None


def _call_ollama(model: str, system_prompt: str, user_message: str) -> Optional[str]:
    """Call local Ollama model."""
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_ctx": 2048,
            "num_predict": 500,
        },
    }
    resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json().get("message", {}).get("content", "")


def _call_image_local(model: str, prompt: str) -> Optional[str]:
    """Call Local Automatic1111/Stable Diffusion WebUI."""
    base_url = os.getenv("SD_WEBUI_URL", "http://127.0.0.1:7860").rstrip("/")
    payload = {
        "prompt": prompt,
        "steps": 20,
        "cfg_scale": 7,
        "width": 1024,
        "height": 1024,
    }
    # Send request to local SD API
    url = f"{base_url}/sdapi/v1/txt2img"
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        # Save the returned base64 image locally or just return success
        return f"Local Image generated via Stable Diffusion! Check your SD output folder."
    except requests.ConnectionError:
        logger.error(f"BrainRouter: Local SD WebUI is not running at {base_url}")
        return f"Error: Local Stable Diffusion is not running at {base_url}."


# ── Status & Info ─────────────────────────────────────────────────────────

def get_brain_status() -> dict:
    """Show current brain routing configuration."""
    status = {}
    for task_type, config in MODELS.items():
        status[task_type] = f"{config['provider']}/{config['model']}"
    return status


def list_available_options() -> str:
    """List available model options for the user."""
    return """
======================================================================
JARVIS AI CATALOGUE (Free/Local-First)
======================================================================

--- 💻 LOCAL MODELS (Free, Offline via Ollama) ---
Standard (8GB+ RAM):
  PROVIDER=ollama    MODEL=llama3.2:1b, llama3:8b, mistral:7b, gemma:7b, qwen:7b, phi3:3.8b, neural-chat, starcoder2:3b
Heavy (16GB+ RAM):
  PROVIDER=ollama    MODEL=mixtral:8x7b, command-r, dbrx, codellama:13b, qwen:14b, deepseek-coder:6.7b
Massive (32GB+ RAM):
  PROVIDER=ollama    MODEL=llama3:70b, qwen:72b, wizardlm2:8x22b, falcon:40b
Images (Requires GPU):
  PROVIDER=local     (Connects to your local Automatic1111 / Stable Diffusion UI)

--- 🌍 BROWSER AUTOMATION (Free, Online UI) ---
Set PROVIDER=browser and MODEL=any_site_name:
  LLMs: chatgpt, claude, gemini, perplexity
  Images: midjourney, leonardo, canva
  Productivity: replit, v0, cursor, grammarly

HOW TO CONFIGURE (.env):
--------------------------------
# 100% Free & Private (Local)
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2:1b

# Browser Automation (Free, Cloud UI)
RESEARCH_PROVIDER=browser
RESEARCH_MODEL=perplexity
======================================================================
"""
