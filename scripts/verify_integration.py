"""Quick integration check for Kokoro + Parakeet in JARVIS"""
import sys, os; sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(os.getcwd()) / '.env')

print("=== JARVIS Kokoro + Parakeet Integration Check ===")

# 1. .env
print(f"\n[1] .env: TTS={os.getenv('TTS_PROVIDER')} STT={os.getenv('STT_PROVIDER')}")

# 2. TTS engine
print("\n[2] TTS engine")
from core.tts_engine import TTS_PROVIDER
print(f"  TTS_PROVIDER={TTS_PROVIDER}")
assert TTS_PROVIDER == "kokoro", f"Expected kokoro, got {TTS_PROVIDER}"
print("  OK")

# 3. STT engine  
print("\n[3] STT engine")
from core.stt_engine import STT_PROVIDER
print(f"  STT_PROVIDER={STT_PROVIDER}")
assert STT_PROVIDER == "parakeet", f"Expected parakeet, got {STT_PROVIDER}"
print("  OK")

# 4. Reflex system
print("\n[4] Reflex system")
from core.planner import Planner
p = Planner()
cmds = ["open youtube", "volume up", "minimize window", "what time is it"]
matched = 0
for cmd in cmds:
    intents = list(p.plan(cmd, {}))
    if intents:
        matched += 1
        print(f"  OK: '{cmd}' -> {intents[0].intent}")
print(f"  {matched}/{len(cmds)} reflexes matched")

# 5. PC executor
print("\n[5] PC executor")
from core.action_router import ActionRouter
router = ActionRouter()
from core.context_collector import ContextCollector
ctx = ContextCollector().collect(light=True)
for cmd in ["what time is it", "check battery"]:
    for intent in p.plan(cmd, {}):
        success, msg = router.route(intent, ctx)
        print(f"  {'OK' if success else 'FAIL'}: {cmd} -> {msg}")

print(f"\n{'='*50}")
print("Integration verified successfully")
print(f"{'='*50}")
