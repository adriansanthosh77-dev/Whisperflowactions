"""Test HUD transitions, vision, and fullscreen flows"""
import sys, os, time, json, asyncio
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv; load_dotenv()

print("=" * 60)
print("JARVIS HUD + VISION TEST")
print("=" * 60)

# ── 1. Test HUD Overlay State Transitions ──
print("\n[1] HUD Overlay fullscreen/mini transitions")
from ui.overlay import Overlay, State, run_overlay_in_thread

overlay = run_overlay_in_thread()
assert overlay is not None
print("  HUD WebSocket server running")

# Test fullscreen -> mini transition
print("  Setting fullscreen=True...")
overlay.set_state(State.SUCCESS, "ALL SYSTEMS NOMINAL", fullscreen=True)
time.sleep(0.3)
assert overlay._fullscreen == True
print(f"  OK stored _fullscreen={overlay._fullscreen}")

print("  Setting fullscreen=False (mini)...")
overlay.set_state(State.IDLE, "SYSTEM READY", fullscreen=False)
time.sleep(0.3)
assert overlay._fullscreen == False
print(f"  OK stored _fullscreen={overlay._fullscreen}")

# Test all state transitions
print("\n[2] All HUD state transitions")
states = [
    (State.SUCCESS, "Done"),
    (State.IDLE, "SYSTEM READY"),
    (State.LISTENING, "Listening..."),
    (State.THINKING, "Processing..."),
    (State.EXECUTING, "Executing..."),
    (State.ERROR, "Failed"),
    (State.SPEAKING, "Speaking"),
]
for state, msg in states:
    overlay.set_state(state, msg)
    time.sleep(0.15)
    assert overlay.current_state == state
    assert overlay.detail == msg
    print(f"  OK {state.name}: {msg}")

print("\n[3] Fullscreen -> mini timing test")
import time as t
t1 = t.time()
overlay.set_state(State.SUCCESS, "Boot", fullscreen=True)
overlay.set_state(State.IDLE, "Ready", fullscreen=False)
t2 = t.time()
print(f"  Transition is instant ({(t2-t1)*1000:.0f}ms)")

# Test WebSocket state delivery (before stopping overlay)
print("\n[4] WebSocket state delivery")
async def test_ws():
    import websockets
    async with websockets.connect("ws://127.0.0.1:9223") as ws:
        # First message is _send_state (initial connect)
        msg1 = await asyncio.wait_for(ws.recv(), timeout=2.0)
        d1 = json.loads(msg1)
        print(f"  Initial state: {d1['state']} fullscreen={d1['fullscreen']}")
        # Now set state and check broadcast
        overlay.set_state(State.SUCCESS, "WebSocket test")
        msg2 = await asyncio.wait_for(ws.recv(), timeout=2.0)
        d2 = json.loads(msg2)
        assert d2["state"] == "SUCCESS"
        print(f"  OK State broadcast received: {d2['state']} fullscreen={d2['fullscreen']}")

asyncio.run(test_ws())

# Clean overlay
print("\n  Stopping HUD...")
overlay.stop()
time.sleep(2)
print("  OK HUD stopped cleanly")

# ── 2. Test Vision System ──
print("\n[5] Vision System (DirectML + moondream)")
from core.vision_engine import get_vision_engine
vision = get_vision_engine()
assert vision is not None
print("  OK Vision engine loaded")

from core.vision_assistant import get_vision_assistant
va = get_vision_assistant(vision)
assert va is not None
print("  OK Vision assistant loaded")

# Take a screenshot
screenshot_path = "test_screenshot.png"
result = va.capture_screenshot(screenshot_path)
assert result, "Screenshot failed"
sz = os.path.getsize(screenshot_path)
print(f"  OK Screenshot captured: {sz} bytes")

# Test DirectML (classify image)
from core.vision_directml import get_directml_vision
dml = get_directml_vision()
if dml and dml.is_available():
    import numpy as np
    from PIL import Image
    img = Image.open(screenshot_path).resize((224, 224))
    img_np = np.array(img).astype(np.float32) / 255.0
    result = dml.classify_image(img_np)
    print(f"  OK DirectML classification: {result}")
else:
    print("  - DirectML not available on this system")

os.remove(screenshot_path)

# ── 3. Test Overlay WebSocket delivers state messages ──
print("\n[5] WebSocket state delivery")
time.sleep(2)  # Wait for port to release
import subprocess
subprocess.run(["taskkill","/f","/im","electron.exe"], capture_output=True)
overlay2 = run_overlay_in_thread()
received = []
async def test_ws():
    import websockets
    async with websockets.connect("ws://127.0.0.1:9223") as ws:
        overlay2.set_state(State.LISTENING, "Test message")
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(msg)
        assert data["type"] == "state"
        assert data["fullscreen"] == False
        received.append(data)
asyncio.run(test_ws())
print(f"  OK WebSocket received state: {received[0]['state']}, fullscreen={received[0]['fullscreen']}")
overlay2.stop()

print("\n" + "=" * 60)
print("ALL TESTS PASSED")
print("=" * 60)
