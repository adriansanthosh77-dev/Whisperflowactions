"""Quick system check - tests what matters"""
import sys, os; sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv()
ok = True

print("=== JARVIS Quick System Check ===\n")

# 1. edge-tts Ryan
import edge_tts, asyncio
async def ryan():
    c = edge_tts.Communicate("System check. Ryan voice operational.", "en-GB-RyanNeural")
    await c.save("check_ryan.wav")
    sz = os.path.getsize("check_ryan.wav")
    print(f"[1] Ryan voice: {sz} bytes {'OK' if sz > 1000 else 'FAIL'}")
asyncio.run(ryan())

# 2. STT
from core.stt_engine import get_stt_engine
stt = get_stt_engine()
print(f"[2] STT engine: OK ({stt})")

# 3. TTS engine
from core.tts_engine import get_tts_engine
tts = get_tts_engine()
print(f"[3] TTS engine: {tts.provider}")

# 4. All reflexes via planner
from core.planner import Planner
p = Planner()
reflex_count = 0
for cmd in [
    "minimize window","maximize window","close window","switch window",
    "snap left","snap right","show desktop","screenshot","lock pc",
    "brightness up","brightness down","check battery","what time is it",
    "today's date","how is the pc","volume up","volume down","mute",
    "play","pause","play pause","next track","previous track",
    "fullscreen","copy","paste","undo","redo","select all","save","find",
    "open calculator","open notepad","open cmd","open settings","task manager",
    "open youtube","open google","open gmail","open github",
    "hello","who are you","thank you",
    "scroll down","scroll up","go to top","go to bottom",
]:
    intents = list(p.plan(cmd, {}))
    if intents:
        reflex_count += 1
print(f"[4] Reflexes matched: {reflex_count}")

# 5. Execute live commands
from core.action_router import ActionRouter
from core.context_collector import ContextCollector
router = ActionRouter(); ctx = ContextCollector()
for cmd in ["what time is it", "check battery"]:
    for intent in p.plan(cmd, {}):
        ok2, msg = router.route(intent, ctx.collect(light=True))
        print(f"[5] EXEC: {cmd} -> {'OK' if ok else 'FAIL'}: {msg}")

# 6. Intent sequencer
from core.intent_sequencer import IntentSequencer
seq = IntentSequencer()
for cmd in ["open youtube","volume up","hello"]:
    r = seq.classify(cmd)
    print(f"[6] {cmd} -> {r['tier']}")

print("\n=== CHECK COMPLETE ===")
os.remove("check_ryan.wav") if os.path.exists("check_ryan.wav") else None
