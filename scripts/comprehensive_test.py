"""
Comprehensive test suite — 80+ assertions covering all modules and all changes.
"""

import os
import sys
import json
import time
import tempfile
import inspect
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

passed = 0
failed = 0
total = 0

def t(name, cond, detail=""):
    global passed, failed, total
    total += 1
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f"  -- {detail}" if detail else ""))

print("=" * 60)
print("COMPREHENSIVE TEST SUITE (80+ assertions)")
print("=" * 60)

# ── 1. BRAIN ROUTER ──
from core.brain_router import MODELS, call_model, get_brain_status, list_available_options

t("BR-01: IMAGE_PROVIDER default is ollama", MODELS["image_generation"]["provider"] == "ollama")
t("BR-02: IMAGE_MODEL default is llava", MODELS["image_generation"]["model"] == "llava")
t("BR-03: ENGINEERING_PROVIDER default is ollama", MODELS["engineering_cad"]["provider"] == "ollama")
t("BR-04: ENGINEERING_MODEL default is llama3.2:1b", MODELS["engineering_cad"]["model"] == "llama3.2:1b")
t("BR-05: GAMING_PROVIDER default is ollama", MODELS["game_development"]["provider"] == "ollama")
t("BR-06: GAMING_MODEL default is llama3.2:1b", MODELS["game_development"]["model"] == "llama3.2:1b")
t("BR-07: AUTOMATION_PROVIDER default is ollama", MODELS["automation_workflow"]["provider"] == "ollama")
t("BR-08: AUTOMATION_MODEL default is llama3.2:1b", MODELS["automation_workflow"]["model"] == "llama3.2:1b")
t("BR-09: CODING_PROVIDER still ollama (was already)", MODELS["coding"]["provider"] == "ollama")
t("BR-10: video call_model returns paid message", "paid" in (call_model("video_generation", "", "test") or "").lower())
t("BR-11: image call_model returns non-None string", call_model("image_generation", "", "test a cat") is not None)
t("BR-12: list_available_options no ONLINE API", "ONLINE API" not in list_available_options())
t("BR-13: list_available_options still shows LOCAL", "LOCAL" in list_available_options())
t("BR-14: get_brain_status has all keys", set(get_brain_status().keys()) == set(MODELS.keys()))
t("BR-15: No _call_openai function", not hasattr(sys.modules["core.brain_router"], "_call_openai"))
t("BR-16: No _call_anthropic function", not hasattr(sys.modules["core.brain_router"], "_call_anthropic"))
t("BR-17: No _call_video_replicate", not hasattr(sys.modules["core.brain_router"], "_call_video_replicate"))
t("BR-18: No _call_3d_meshy", not hasattr(sys.modules["core.brain_router"], "_call_3d_meshy"))

# ── 2. PLANNER ──
from core.planner import Planner

p = Planner()
t("PL-01: Planner model defaults to OLLAMA_MODEL", p.model == "llama3.2:1b")
t("PL-02: No OPENAI_MODEL module var", "OPENAI_MODEL" not in dir(sys.modules["core.planner"]))
t("PL-03: No _has_openai_key function", "_has_openai_key" not in dir(sys.modules["core.planner"]))
t("PL-04: No _stream_plan_openai function", "_stream_plan_openai" not in dir(sys.modules["core.planner"]))

planner_src = inspect.getsource(sys.modules["core.planner"])
t("PL-05: file_type_match count <= 2", planner_src.count("file_type_match") <= 2)
t("PL-06: minimize_match count <= 1", planner_src.count("minimize_match") <= 1)
t("PL-07: maximize_match count <= 1", planner_src.count("maximize_match") <= 1)
t("PL-08: close_match count <= 1", planner_src.count("close_match") <= 1)
t("PL-09: remind_match reflex exists", "remind_match" in planner_src)
t("PL-10: pc_reflexes dict exists", "pc_reflexes" in planner_src)
t("PL-11: list_reflexes returns list", isinstance(p.list_reflexes(), list))

# ── 3. PC EXECUTOR ──
from executors.pc_executor import PCExecutor

pc_src = inspect.getsource(sys.modules["executors.pc_executor"])
t("PC-01: _tap_keys uses platform_keys", "platform_keys" in inspect.getsource(PCExecutor._tap_keys))
t("PC-02: KEY_CODES dict removed", "KEY_CODES" not in pc_src)
t("PC-03: close_window uses platform_close", "platform_close()" in pc_src)
t("PC-04: minimize_window uses platform_minimize", "platform_minimize()" in pc_src)
t("PC-05: maximize_window uses platform_maximize", "platform_maximize()" in pc_src)
t("PC-06: shell=True removed from _find_matches", "shell=True" not in pc_src.split("_find_matches")[1].split("def ")[0] if "_find_matches" in pc_src else True)
t("PC-07: Path.rglob in _find_matches", "rglob" in pc_src)
t("PC-08: LLM_PROVIDER default ollama", 'provider = os.getenv("LLM_PROVIDER", "ollama")' in pc_src)

# ── 4. TTS ENGINE ──
from core.tts_engine import TTSEngine

tts = TTSEngine()
t("TS-01: TTS provider default piper", tts.provider == "piper")
t("TS-02: No api_key attribute", not hasattr(tts, "api_key") or tts.api_key is None)
t("TS-03: No _speak_openai method", not hasattr(tts, "_speak_openai"))
tts_src = inspect.getsource(sys.modules["core.tts_engine"])
t("TS-04: No openai branch in say()", 'elif self.provider == "openai"' not in tts_src)

# ── 5. GMAIL EXECUTOR ──
from executors.gmail_executor import GmailExecutor

gmail_src = inspect.getsource(GmailExecutor._gpt_summarize)
t("GM-01: _gpt_summarize uses Ollama", "OLLAMA_BASE_URL" in gmail_src)
t("GM-02: _gpt_summarize no OpenAI URL", "api.openai.com" not in gmail_src)
t("GM-03: _gpt_summarize has fallback msg", "Summary unavailable" in gmail_src)

# ── 6. FEEDBACK STORE (Reminders) ──
from core.feedback_store import FeedbackStore

db_path = Path(tempfile.gettempdir()) / f"test_jarvis_{int(time.time())}.db"
db = FeedbackStore(db_path)
t("FB-01: set_reminder returns int", isinstance(db.set_reminder("test", 0), int))
rid = db.set_reminder("remind me to test", 0)
due = db.get_due_reminders()
t("FB-02: get_due_reminders returns items", len(due) >= 1)
t("FB-03: Reminder text preserved", any(r["text"] == "remind me to test" for r in due))
clear_id = due[0]["id"] if due else rid
db.clear_reminder(clear_id)
t("FB-04: clear_reminder works", len(db.get_due_reminders()) == 0)
t("FB-05: reminders table exists", "reminders" in [r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()])
db.close()
os.unlink(db_path)

# ── 7. OVERLAY ──
from ui.overlay import Overlay, State

o = Overlay()
t("OV-01: startup_complete default False", o.startup_complete is False)
o.startup_complete = True
t("OV-02: startup_complete setter works", o.startup_complete is True)
t("OV-03: _first_wake_done updated by property", o._first_wake_done is True)
t("OV-04: stop does not crash", (o.stop(), True)[1])
t("OV-05: State has all expected values", all(s in dir(State) for s in ["IDLE", "LISTENING", "THINKING", "EXECUTING", "SUCCESS", "ERROR", "SPEAKING"]))

# ── 8. TRAY ──
from ui.tray import TrayIcon

tray = TrayIcon(on_show=lambda: None, on_quit=lambda: None, on_toggle_listen=lambda: None)
t("TR-01: TrayIcon instantiates", tray is not None)
t("TR-02: TrayIcon stores callbacks", None not in (tray._on_show, tray._on_quit, tray._on_toggle_listen))
t("TR-03: stop without icon no crash", (tray.stop(), True)[1])

# ── 9. CALENDAR EXECUTOR ──
from executors.calendar_executor import CalendarExecutor

cal = CalendarExecutor()
t("CA-01: CalendarExecutor instantiates", cal is not None)
t("CA-02: CalendarExecutor extends BaseExecutor", "BaseExecutor" in [c.__name__ for c in type(cal).__mro__])

# ── 10. ORCHESTRATOR ──
import core.orchestrator as orch_module

orch_src = inspect.getsource(orch_module)
t("OR-01: _start_reminder_checker exists", "_start_reminder_checker" in orch_src)
t("OR-02: reminder handler in execute flow", 'step.intent == "reminder"' in orch_src)
t("OR-03: on_segment in dictation", "on_segment" in orch_src)
t("OR-04: SLEEP_TIMEOUT_SECONDS env", "SLEEP_TIMEOUT_SECONDS" in orch_src)
t("OR-05: WEATHER_DESCRIPTION env", "WEATHER_DESCRIPTION" in orch_src)
t("OR-06: wttr.in fetch", "wttr.in" in orch_src)
t("OR-07: run_tray_in_thread wired", "run_tray_in_thread" in orch_src)
t("OR-08: stop method exists", "def stop" in orch_src)
t("OR-09: _history buffer 50", "[-50:]" in orch_src)
t("OR-10: Cinematic sleep reduced", "time.sleep(0.3)" in orch_src)

# ── 11. STT ENGINE ──
from core.stt_engine import STTEngine

transcribe_sig = inspect.signature(STTEngine.transcribe)
t("ST-01: on_segment param in transcribe", "on_segment" in transcribe_sig.parameters)
stt_src = inspect.getsource(STTEngine.transcribe)
t("ST-02: on_segment called with segment.text", "on_segment(segment.text)" in stt_src)

# ── 12. IMPORT INTEGRITY ──
import executors

t("IM-01: CalendarExecutor in __all__", "CalendarExecutor" in executors.__all__)
t("IM-02: PCExecutor in __all__", "PCExecutor" in executors.__all__)
t("IM-03: GmailExecutor in __all__", "GmailExecutor" in executors.__all__)
t("IM-04: BaseExecutor in __all__", "BaseExecutor" in executors.__all__)

# ── 13. MEMORY STORE ──
from core.memory_store import get_memory

mem = get_memory()
t("ME-01: get_memory singleton", mem is get_memory())
t("ME-02: add fact works", (mem.add("test fact", "test"), True)[1])
t("ME-03: recall returns results", len(mem.recall("test")) >= 1)

# ── 14. PLATFORM ──
from core.platform_utils import IS_WINDOWS, IS_MAC, IS_LINUX, send_keys

t("PLT-01: IS_WINDOWS bool", isinstance(IS_WINDOWS, bool))
t("PLT-02: IS_MAC bool", isinstance(IS_MAC, bool))
t("PLT-03: IS_LINUX bool", isinstance(IS_LINUX, bool))
t("PLT-04: send_keys callable", callable(send_keys))

# ── 15. DOCKER FILES ──
t("DK-01: Dockerfile exists", Path("Dockerfile").exists())
t("DK-02: docker-compose.yml exists", Path("docker-compose.yml").exists())
t("DK-03: docker-entrypoint.sh exists", Path("scripts/docker-entrypoint.sh").exists())
t("DK-04: setup_docker.sh exists", Path("scripts/setup_docker.sh").exists())
t("DK-05: setup_docker.ps1 exists", Path("scripts/setup_docker.ps1").exists())
t("DK-06: download_binaries.ps1 exists", Path("scripts/download_binaries.ps1").exists())

# ── 16. JSON / FILE INTEGRITY ──
from core.brain_router import _call_image_local
t("FI-01: _call_image_local preserved (local SD)", callable(_call_image_local))
t("FI-02: .env.example has no paid API keys", all(
    k not in open(".env.example").read()
    for k in ["OPENAI_API_KEY=", "ANTHROPIC_API_KEY=", "MESHY_API_KEY="]
))

print()
print("=" * 60)
print(f"RESULTS: {passed} passed / {total} total, {failed} failed ({passed/total*100:.0f}%)")
print("=" * 60)

if failed > 0:
    sys.exit(1)
