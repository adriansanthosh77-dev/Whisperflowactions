"""
JARVIS Comprehensive Test - Streamlined
"""
import sys, os, time, json, threading, io, wave
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv()

PASS = 0; FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS: {name}")
    except Exception as e:
        FAIL += 1
        import traceback
        traceback.print_exc()
        print(f"  FAIL: {name}: {e}")

print("=" * 60)
print("JARVIS COMPREHENSIVE TEST")
print("=" * 60)
print()

# ── 1. TTS ──────────────────────────────────────────────────────
print("[1] TTS Engine")
def tts_test():
    from core.tts_engine import get_tts_engine
    tts = get_tts_engine()
    assert tts.provider in ("edge", "powershell", "kokoro", "piper")
    # Test edge-tts output if available
    try:
        import edge_tts, asyncio
        async def gen():
            c = edge_tts.Communicate("JARVIS system test.", "en-GB-RyanNeural")
            await c.save("test_ryan_voice.wav")
            sz = os.path.getsize("test_ryan_voice.wav")
            assert sz > 1000, f"Audio too small: {sz}"
        asyncio.run(gen())
    except ImportError:
        # edge_tts not installed — verify engine loads without crash
        pass
test(f"TTS engine loads ({os.getenv('TTS_PROVIDER', 'default')})", tts_test)

# ── 2. STT ──────────────────────────────────────────────────────
print("[2] STT (faster-whisper)")
def stt_test():
    from core.stt_engine import get_stt_engine
    stt = get_stt_engine()
    import numpy as np
    sr = 16000
    t = np.linspace(0, 1, sr)
    audio = (np.sin(2 * np.pi * 200 * t * 0.3) * 30000).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    result = stt.transcribe(buf.getvalue())
    # Synthetic audio may not transcribe - but shouldn't crash
test("STT processes audio without crash", stt_test)

# ── 3. ALL 57 REFLEXES ──────────────────────────────────────────
CMDS = [
    ("minimize window", "pc_action"),("maximize window", "pc_action"),
    ("close window", "pc_action"),("switch window", "pc_action"),
    ("snap left", "pc_action"),("snap right", "pc_action"),
    ("show desktop", "pc_action"),("take a screenshot", "pc_action"),
    ("lock pc", "pc_action"),("brightness up", "pc_action"),
    ("brightness down", "pc_action"),("check battery", "pc_action"),
    ("what time is it", "pc_action"),("current time", "pc_action"),
    ("today's date", "pc_action"),("how is the pc", "pc_action"),
    ("play", "pc_action"),("pause", "pc_action"),("play pause", "pc_action"),
    ("next track", "pc_action"),("previous track", "pc_action"),
    ("volume up", "pc_action"),("volume down", "pc_action"),
    ("mute", "pc_action"),("fullscreen", "pc_action"),
    ("copy", "pc_action"),("paste", "pc_action"),("undo", "pc_action"),
    ("redo", "pc_action"),("select all", "pc_action"),("save", "pc_action"),
    ("find", "pc_action"),("open calculator", "pc_action"),
    ("open notepad", "pc_action"),("open cmd", "pc_action"),
    ("open terminal", "pc_action"),("open powershell", "pc_action"),
    ("open settings", "pc_action"),("task manager", "pc_action"),
    ("open youtube", "pc_action"),("open google", "pc_action"),
    ("open gmail", "pc_action"),("open github", "pc_action"),
    ("open reddit", "pc_action"),("open amazon", "pc_action"),
    ("open netflix", "pc_action"),("open spotify", "pc_action"),
    ("open chatgpt", "pc_action"),("open claude", "pc_action"),
    ("hello", "chat"),("who are you", "chat"),("thank you", "chat"),
    ("scroll down", "pc_action"),("scroll up", "pc_action"),
    ("go to top", "pc_action"),("go to bottom", "pc_action"),
]
print(f"[3] All {len(CMDS)} Reflexes")
def all_reflexes():
    from core.planner import Planner
    p = Planner()
    for cmd, expected in CMDS:
        results = list(p.plan(cmd, {}))
        assert results, f"No plan for '{cmd}'"
        assert results[0].intent == expected, f"'{cmd}'={results[0].intent}"
test(f"{len(CMDS)}/{len(CMDS)} reflexes correct", all_reflexes)

# ── 4. PC EXECUTION ─────────────────────────────────────────────
print("[4] PC Executor (live)")
def pc_exec():
    from core.planner import Planner
    from core.action_router import ActionRouter
    from core.context_collector import ContextCollector
    p = Planner(); router = ActionRouter(); ctx = ContextCollector()
    for cmd in ["what time is it", "check battery"]:
        for intent in p.plan(cmd, {}):
            success, msg = router.route(intent, ctx.collect(light=True))
            assert success, f"'{cmd}' failed: {msg}"
test("PC executor runs commands", pc_exec)

# ── 5. INTENT SEQUENCER ─────────────────────────────────────────
print("[5] IntentSequencer")
def intent_seq():
    from core.intent_sequencer import IntentSequencer
    seq = IntentSequencer()
    for cmd, expected in [("open youtube","REFLEX"),("volume up","REFLEX"),
        ("research AI","RESEARCH"),("write code","CODING"),
        ("hello","REFLEX")]:
        r = seq.classify(cmd)
        assert r["tier"] == expected, f"'{cmd}'={r['tier']}"
test("IntentSequencer classifies", intent_seq)

# ── 6. VISION ───────────────────────────────────────────────────
print("[6] Vision")
def vision():
    from core.vision_engine import get_vision_engine
    v = get_vision_engine()
    assert v is not None
    from core.vision_assistant import get_vision_assistant
    va = get_vision_assistant(v)
    assert va is not None
test("Vision systems load", vision)

# ── 7. HUD ──────────────────────────────────────────────────────
print("[7] HUD Overlay")
def hud():
    from ui.overlay import Overlay, State, run_overlay_in_thread
    overlay = run_overlay_in_thread()
    overlay.set_state(State.SUCCESS, "Test", fullscreen=True)
    overlay.set_state(State.IDLE, "Ready", fullscreen=False)
    overlay.set_state(State.LISTENING, "Listening")
    assert overlay.current_state == State.LISTENING
    overlay.stop()
test("HUD initializes and transitions", hud)

# ── 8. FULL ORCHESTRATOR ────────────────────────────────────────
print("[8] Orchestrator Pipeline")
def orch():
    from core.orchestrator import JARVISOrchestrator
    o = JARVISOrchestrator()
    assert o.intent_sequencer is not None
    from core.context_collector import ContextCollector
    ctx = ContextCollector().collect(light=True)
    for cmd in ["what time is it", "check battery"]:
        success = o._execute_text(cmd, ctx)
        assert success, f"Pipeline failed '{cmd}'"
    o.tts.say("Test complete. All systems operational.", wait=False)
    o.overlay.stop()
    try:
        import subprocess
        if hasattr(o.overlay, '_electron_process') and o.overlay._electron_process:
            subprocess.run(["taskkill","/f","/pid",str(o.overlay._electron_process.pid)], capture_output=True)
    except Exception:
        pass
test("Orchestrator pipeline end-to-end", orch)

print()
print(f"RESULTS: {PASS}/{PASS+FAIL} passed, {FAIL} failed")

# Cleanup
if os.path.exists("test_ryan_voice.wav"):
    os.remove("test_ryan_voice.wav")
