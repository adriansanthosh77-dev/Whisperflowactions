# JARVIS MVP — Build Plan (✅ ALL 9 PHASES COMPLETE)

## Architecture Vision

```
[Audio Capture] → [VAD] → [STT (Whisper)] → [Planner] → [Executor] → [Action]
                                          ↗              ↙
                                   [Reflexes (fast)]  [LLM (slow)]
```

- **Reflexes**: 227 pre-programmed commands executing in milliseconds (no AI)
- **LLM**: Multi-step or complex tasks that need reasoning
- **Cross-platform**: Windows, macOS, Linux

---

## Phase 1: Audio & STT Reliability ✅

**Goal**: Word-perfect transcription on any computer, short or long phrases.

| # | Task | Detail | Status |
|---|------|--------|--------|
| 1.1 | **Dual-model STT** | `tiny.en` for fast reflexes, `medium.en`/`large-v3` for long phrases. Auto-select: <3s → tiny, >3s → large | ✅ |
| 1.2 | **Fix beam search** | `beam_size=1` → `beam_size=5` | ✅ |
| 1.3 | **Fix `_clean_text()`** | Stop stripping `"you"`, `"thanks"`. Only remove real hallucinations | ✅ |
| 1.4 | **Adaptive initial prompt** | Short: trigger-word prompt. Long: no prompt (avoids bias) | ✅ |
| 1.5 | **Adaptive VAD** | Short: 500ms silence. Long: 1500ms silence | ✅ |
| 1.6 | **Word-level confidence** | Per-word probability from faster-whisper. Flag if <0.6 | ✅ |
| 1.7 | **HUD low-confidence feedback** | Show low-confidence words. User re-speaks | ✅ |
| 1.8 | **Adaptive gain control** | Targets -12dBFS peak. No hardcoded 3x clipping | ✅ |
| 1.9 | **Noise floor / gate** | Dynamic tracking per-environment | ✅ |
| 1.10 | **Long recording support** | Configurable up to 120s. Wall-clock timeout | ✅ |
| 1.11 | **Fix callback thread safety** | `put_nowait()` in callback. `threading.Event` | ✅ |
| 1.12 | **Cross-platform mic detection** | `sounddevice.query_devices()` on all OSes | ✅ |
| 1.13 | **GPU auto-detect** | CUDA → MPS → CPU with appropriate compute_type | ✅ |
| 1.14 | **Proper audio cleanup** | `cleanup()` stops stream, releases mic | ✅ |
| 1.15 | **Single `load_dotenv()`** | Only in `orchestrator.py`, removed from 7 other files | ✅ |

---

## Phase 2: System-Wide Dictation Mode ✅

**Goal**: Speak and text appears in any app — Notepad, VS Code, browser, terminal, chat.

| # | Task | Detail | Status |
|---|------|--------|--------|
| 2.1 | **Dictation mode state machine** | `_dictation_active` flag. Bypasses reflex/command matching | ✅ |
| 2.2 | **Toggle: hotkey** | `Ctrl+Shift+D` to start/stop | ✅ |
| 2.3 | **Toggle: voice command** | "start dictation" / "stop dictation" reflexes | ✅ |
| 2.4 | **Fast text injection** | Save clipboard → paste → restore. Works in 95%+ apps | ✅ |
| 2.5 | **Fallback: char-by-char** | `pynput` keyboard simulation when clipboard blocked | ✅ |
| 2.6 | **Live HUD transcription** | Shows real-time partial transcription | ✅ |
| 2.7 | **Target app dictation** | "dictate in discord" → focus app + dictation mode | ✅ |
| 2.8 | **Punctuation from speech** | Whisper outputs punctuation naturally | ✅ |

---

## Phase 3: Cross-Platform PC Reflex Execution ✅

**Goal**: 200+ PC reflexes work on Win/Mac/Linux without errors.

| # | Task | Detail | Status |
|---|------|--------|--------|
| 3.1 | **Platform abstraction layer** | `core/platform.py` with Win/Mac/Linux: app launch, volume, media, window mgmt, system info, keyboard | ✅ |
| 3.2 | **Rewrite `pc_executor.py`** | Replaced all Win32 calls with platform abstraction | ✅ |
| 3.3 | **Safe clipboard everywhere** | All clipboard ops save/restore in try/finally | ✅ |
| 3.4 | **Fix command injection** | Removed every `shell=True`. Use arg lists | ✅ |
| 3.5 | **Fix `CoInitialize` leak** | Paired `CoUninitialize()` | ✅ |
| 3.6 | **App launching per OS** | Win: `os.startfile`. Mac: `open -a`. Linux: `xdg-open` | ✅ |

---

## Phase 4: Browser Automation (Non-Disruptive) ✅

**Goal**: Browser executes tasks without closing user's browser or stealing tabs.

| # | Task | Detail | Status |
|---|------|--------|--------|
| 4.1 | **Remove browser killing** | `_cleanup_browsers()` never kills processes | ✅ |
| 4.2 | **Separate persistent profile** | `data/browser_profile/jarvis_profile` — isolated, persistent logins | ✅ |
| 4.3 | **Visible mode (watch)** | Separate Chrome window + CDP port | ✅ |
| 4.4 | **Stealth — Windows** | Obscura binary | ✅ |
| 4.5 | **Stealth — Mac/Linux** | Headless Chrome + separate profile | ✅ |
| 4.6 | **CDP security** | Bind to `127.0.0.1` only. No `--remote-allow-origins` | ✅ |
| 4.7 | **Browser detection per OS** | Win: registry. Mac: paths. Linux: `which` | ✅ |
| 4.8 | **Fix `check_health` double-def** | Removed duplicate. Lightweight version only | ✅ |
| 4.9 | **Fix `with_retry`** | Actual retry with exponential backoff (3 attempts) | ✅ |
| 4.10 | **Thread-safe CDP state** | `_state_lock` on `_action_events`, `_teach_events` | ✅ |

---

## Phase 5: Fix Critical Bugs ✅

| # | Bug | Fix | Status |
|---|-----|-----|--------|
| 5.1 | orchestrator success tracking | `_execute_text` returns `bool` | ✅ |
| 5.2 | overlay `_first_wake_done` | Set to `True` after first wake | ✅ |
| 5.3 | Gmail Ctrl+Enter | Correct `keyDown`/`keyUp`, no bogus `modifiers` | ✅ |
| 5.4 | `browser_executor` fall-through | Added `"auto"` to return check | ✅ |
| 5.5 | vision engine `keep_alive: 0` | Changed to `"10m"` | ✅ |
| 5.6 | WhatsApp Enter keys | Corrected from `char` events to `keyDown`/`keyUp` | ✅ |
| 5.7 | memory store | Thread lock, absolute path, cleaned imports | ✅ |
| 5.8 | singleton `get_*()` | `_MEMORY_LOCK` added to `get_memory()` | ✅ |

---

## Phase 6: Cross-Platform OCR ✅

| # | Task | Detail | Status |
|---|------|--------|--------|
| 6.1 | **Platform OCR abstraction** | New `core/ocr_adapter.py`. Win: `Windows.Media.Ocr`. Mac: `VNRecognizeTextRequest` via Swift. Linux: `pytesseract` | ✅ |
| 6.2 | **Backward compatibility** | `core/ocr_engine.py` wraps adapter | ✅ |

---

## Phase 7: Cross-Platform Hardware & Diagnostics ✅

| # | Task | Detail | Status |
|---|------|--------|--------|
| 7.1 | **Hardware checker** | Win: WMI. Mac: sysctl + system_profiler. Linux: /proc/meminfo + nvidia-smi | ✅ |
| 7.2 | **Fix overlay Win32 flags** | `creation_flags` gated with `os.name == 'nt'` | ✅ |
| 7.3 | **Doctor tool** | Cross-platform: system info, dependencies, GPU, audio, STT config, Ollama, API keys | ✅ |

---

## Phase 8: Test Infrastructure ✅

| # | Task | Detail | Status |
|---|------|--------|--------|
| 8.1 | Fix machine-specific paths | Replaced `c:\Users\cw_63\...` with relative paths | ✅ |
| 8.2 | Mock `requests.get` | Added `mock_get` to 9 test files | ✅ |
| 8.3 | `pyproject.toml` | Added pytest config | ✅ |

---

## Phase 9: Config & Deps Cleanup ✅

| # | Task | Detail | Status |
|---|------|--------|--------|
| 9.1 | Sync `.env.example` | All 30+ env vars documented | ✅ |
| 9.2 | Remove `sentence-transformers` | Dead 1-2GB dependency removed | ✅ |
| 9.3 | Fix Electron version | `^42.0.1` → `^29.0.0` | ✅ |
| 9.4 | Add `.gitignore` | venv, __pycache__, .env, node_modules, data, *.db, etc. | ✅ |
| 9.5 | Update `executors/__init__.py` | Exports 8 classes | ✅ |

---

## Execution Order

```
Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6-9
(Audio/STT)  (Dictation)  (PC Reflex)  (Browser)    (Bugs)      (Polish)
```

**All phases executed and tested.** See final system test results below.

---

## Final System Test Results

All 9 phases verified with the comprehensive `final_system_test.py` suite:

| Phase | Key Tests | Result |
|-------|-----------|--------|
| 1 | STTResult, clean_text, duration, model loading | ✅ ALL PASS |
| 2 | 5 dictation reflexes, clipboard restore, char-by-char, orchestrator methods | ✅ ALL PASS |
| 3 | Platform detection, battery/CPU, action router, no shell=True | ✅ ALL PASS |
| 4 | No browser killing, isolated profile, CDP security, thread safety, retry | ✅ ALL PASS |
| 5 | execute_text return, vision keep_alive, Gmail/WhatsApp events, memory store | ✅ ALL PASS |
| 6 | OCR missing file, singleton, backward compat | ✅ ALL PASS |
| 7 | Hardware checker (16GB RAM, 2 GPUs), doctor (7 checks), overlay | ✅ ALL PASS |
| 8 | No hardcoded paths, requests.get mocking | ✅ ALL PASS |
| 9 | .env.example synced, sentence-transformers removed, .gitignore, __init__.py | ✅ ALL PASS |
| INTEGRATION | Master test: 50/50 reflexes, 3/4/4/10-step chains | ✅ ALL PASS |

**Files modified across all phases:**
- `core/stt_engine.py` — Dual-model STT, beam search, confidence
- `core/audio_capture.py` — Adaptive gain, long recording, cross-platform mic, cleanup
- `core/orchestrator.py` — STTResult support, dictation mode, hotkey, execute_text fix
- `core/platform.py` — **NEW** Cross-platform PC control abstraction
- `core/memory_store.py` — Thread-safe singleton
- `core/vision_engine.py` — keep_alive fix
- `core/hardware_checker.py` — Cross-platform hardware detection
- `core/doctor.py` — Cross-platform diagnostics
- `core/ocr_adapter.py` — **NEW** Cross-platform OCR
- `core/ocr_engine.py` — Backward-compat wrapper
- `executors/pc_executor.py` — Platform abstraction, clipboard save/restore, no shell=True
- `executors/base_executor.py` — No browser killing, CDP security, thread-safe, with_retry
- `executors/browser_executor.py` — Auto-mode fall-through fix
- `executors/gmail_executor.py` — Correct CDP key events
- `executors/whatsapp_executor.py` — Correct CDP key events
- `executors/__init__.py` — Proper exports
- `ui/overlay.py` — Cross-platform creation flags
- `core/planner.py` — Dictation mode reflexes, removed load_dotenv
- `tests/` — 9 test files: requests.get mocking, path fixes
- `.env.example` — Complete with all 30+ vars
- `.gitignore` — **NEW**
- `requirements.txt` — Cleaned dependencies
- `pyproject.toml` — **NEW**
- `package.json` — Electron version fix

---

## Browser Model Summary

```
┌──────────────────────────────────────────────────────────┐
│                    Browser Strategy                       │
├─────────────────┬───────────────────┬────────────────────┤
│    Visible      │    Stealth        │  Mac Fallback      │
│  (watch mode)   │   (background)    │  (Safari only)     │
├─────────────────┼───────────────────┼────────────────────┤
│ Chrome/Brave/   │ Windows: Obscura  │ safaridriver       │
│ Edge with       │ Mac/Linux:        │ WebDriver          │
│ separate        │ --headless Chrome │ (stubbed)          │
│ profile + CDP   │ + separate prof.  │                    │
├─────────────────┴───────────────────┴────────────────────┤
│ NEVER kills user's browser or tabs                       │
│ Persistent profile at data/browser_profile/jarvis_profile │
│ Remembers logins across restarts                          │
└──────────────────────────────────────────────────────────┘
```

---

## STT Model Strategy

```
Short speech (<3s, likely reflex)  → tiny.en  (fast, ~100ms CPU)
Long speech (>3s, dictation/query)  → medium/large quantized (accurate)
```

- GPU auto-detect: CUDA → MPS → CPU (int8 fallback)
- `beam_size=5` for both (accuracy priority)
- No initial prompt for long phrases (prevents word bias)
- Word-level confidence → HUD feedback → re-speak on low confidence
