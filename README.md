# Whisperflowactions

Voice-first desktop assistant that turns speech into app actions.
Works with **any language**, runs fully local with **Ollama**, or cloud with **OpenAI**.

## What It Does

Whisperflowactions listens for a hotkey, records speech, transcribes it, collects desktop and browser context, parses a structured intent, confirms risky actions, executes through browser automation, and logs the result for future learning.

The current MVP supports:

- WhatsApp Web messages
- Gmail compose, summarize, and professional reply drafting
- Browser page summarization
- Notion task/page creation
- Generic DOM/mouse browser actions such as click, type, and press key
- Adaptive UI memory from successful DOM/text/role/mouse strategies
- Optional screenshot, video, and Playwright trace evidence for UI changes
- Bounded observe-plan-act loop for browser tasks
- **Multi-language speech recognition** (auto-detect or pinned language)
- **Local LLM support** via Ollama (llama3, mistral, phi3, gemma2, etc.)
- **Parallel pipeline** — STT and context collection run concurrently for <3s latency

## Runtime Flow

```text
Ctrl+Space
  -> audio capture with VAD (500ms silence cutoff)
  -> [parallel] Whisper STT (any language) + context collection
  -> LLM intent parse (OpenAI API or local Ollama)
  -> confirmation for risky actions
  -> Playwright executor
  -> selector, role/text, DOM-box mouse, screenshot fallback
  -> repeat observe/act/verify until done or max_steps
  -> before/after DOM + action strategy logging
  -> learning hints for future commands
```

## Project Structure

```text
core/
  orchestrator.py       Main event loop
  audio_capture.py      Microphone input and VAD
  stt_engine.py         Whisper.cpp (multilingual) or OpenAI STT fallback
  intent_parser.py      Speech/context to JSON intent (OpenAI or Ollama)
  context_collector.py  Active window, clipboard, DOM, mouse
  action_router.py      Intent to executor routing
  feedback_store.py     SQLite history, corrections, learning hints

executors/
  base_executor.py      Shared Playwright browser, DOM observation, mouse helpers
  whatsapp_executor.py  WhatsApp Web actions
  gmail_executor.py     Gmail actions
  browser_executor.py   Generic browser, Notion, DOM/mouse actions

models/
  intent_schema.py      Pydantic intent and context models

ui/
  overlay.py            Floating PyQt5 HUD
```

## Setup On Windows

```powershell
.\setup.ps1
```

Then edit `.env` and set:

```text
# Speech-to-text
WHISPER_BIN=whisper-cli
WHISPER_MODEL_PATH=models/ggml-base.bin   # use ggml-base.bin for multilingual
WHISPER_LANGUAGE=auto                     # auto | en | hi | es | ar | zh | ja | etc.

# LLM provider (pick one)
LLM_PROVIDER=openai                       # openai | ollama
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
# — or for fully local —
# LLM_PROVIDER=ollama
# OLLAMA_MODEL=llama3                     # any model pulled via: ollama pull llama3
# OLLAMA_BASE_URL=http://localhost:11434

BROWSER_PROFILE_PATH=C:\Users\you\AppData\Local\JARVIS\browser-profile
RECORD_VIDEO_DIR=data/videos
RECORD_TRACE_DIR=data/traces
```

`RECORD_VIDEO_DIR` and `RECORD_TRACE_DIR` are optional. Enable them when you want JARVIS to keep visual evidence of UI changes and failed actions. Playwright videos are saved when the browser context closes; traces include DOM snapshots and screenshots for debugging.

Use `BROWSER_PROFILE_PATH` for authenticated end-to-end tests. The first run opens a persistent Chromium profile; log into Gmail, WhatsApp Web, and other apps there once, then future runs reuse that session.

Run:

```powershell
python core\orchestrator.py
```

## Setup On macOS/Linux

```bash
chmod +x setup.sh
./setup.sh
python core/orchestrator.py
```

## Hotkey

`Ctrl + Space` starts listening.

## Running Fully Local (No API Keys)

1. Install [Ollama](https://ollama.com) and pull a model:
   ```bash
   ollama pull llama3
   ```
2. Download the multilingual Whisper model:
   ```bash
   # From https://huggingface.co/ggerganov/whisper.cpp
   curl -L -o models/ggml-base.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin
   ```
3. Set `.env`:
   ```text
   LLM_PROVIDER=ollama
   OLLAMA_MODEL=llama3
   WHISPER_LANGUAGE=auto
   WHISPER_MODEL_PATH=models/ggml-base.bin
   ```
4. Run: `python core\orchestrator.py`

No OpenAI API key required. Everything runs on your machine.
