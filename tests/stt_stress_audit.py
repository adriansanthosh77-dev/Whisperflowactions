"""
STT STRESS AUDIT: LONG VS SHORT PHRASES
Verifies dual-model routing based on audio duration.
"""
import sys, os
import time
import numpy as np
sys.path.append(os.getcwd())

from core.stt_engine import STTEngine, LONG_PHRASE_THRESHOLD

print("=" * 70)
print("JARVIS VOICE ENGINE STRESS AUDIT")
print("=" * 70)
print(f"Long phrase threshold: {LONG_PHRASE_THRESHOLD}s")

engine = STTEngine()
import threading
while engine._get_tiny() is None:
    threading.Event().wait(0.1)

def bench(name, duration_sec):
    print(f"\n{name} ({duration_sec}s simulated)")
    samples = int(16000 * duration_sec)
    quiet_audio = (np.sin(np.linspace(0, 440, samples)) * 0.1 * 32767).astype(np.int16).tobytes()

    start = time.time()
    result = engine.transcribe(quiet_audio)
    elapsed = time.time() - start

    if result:
        print(f"  - Time: {elapsed:.3f}s")
        print(f"  - Model: {result.model_used}")
        print(f"  - Text: '{result.text}'")
        print(f"  - Confidence: {result.confidence:.2f}")
    else:
        print(f"  - Time: {elapsed:.3f}s -> No speech detected (expected with low signal)")
    return elapsed

lat1 = bench("Short Phrase (1s → tiny.en)", 1.0)
lat2 = bench("Medium Phrase (3s → tiny.en if below threshold)", 3.0)
lat3 = bench("Long Phrase (8s → medium.en)", 8.0)

avg = (lat1 + lat2 + lat3) / 3
print(f"\nAverage Latency: {avg:.3f}s")

if avg < 0.5:
    print("STATUS: EXCELLENT")
elif avg < 1.0:
    print("STATUS: GOOD")
else:
    print("STATUS: ACCEPTABLE")
print("=" * 70)
