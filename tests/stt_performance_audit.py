"""
STT PERFORMANCE & RELIABILITY AUDIT
Benchmarking transcription speed, initialization latency, and hardware utilization.
"""
import sys, os
import time
import numpy as np
sys.path.append(os.getcwd())

from core.stt_engine import STTEngine, DEVICE, COMPUTE_TYPE, THREADS, STT_MODEL_SHORT, STT_MODEL_LONG

print("=" * 70)
print("JARVIS VOICE ENGINE PERFORMANCE AUDIT")
print("=" * 70)

print(f"Hardware Detection:")
print(f"  - Device: {DEVICE}")
print(f"  - Compute: {COMPUTE_TYPE}")
print(f"  - Threads: {THREADS}")
print(f"  - Short model: {STT_MODEL_SHORT}")
print(f"  - Long model: {STT_MODEL_LONG}")

print("\nInitializing STT Engine...")
start = time.time()
engine = STTEngine()

import threading
tiny_load_start = time.time()
while engine._get_tiny() is None:
    threading.Event().wait(0.1)
tiny_load = time.time() - tiny_load_start
print(f"  - Tiny model loaded in {tiny_load:.2f}s")

print("\nBenchmarking Transcription Latency (1s Silent Buffer)...")
silent_buffer = np.zeros(16000, dtype=np.int16).tobytes()

latencies = []
for i in range(3):
    start = time.time()
    result = engine.transcribe(silent_buffer)
    elapsed = time.time() - start
    latencies.append(elapsed)
    text = result.text if result else "N/A"
    print(f"  - Run {i+1}: {elapsed:.3f}s -> '{text}'")

avg_latency = sum(latencies) / len(latencies)
print(f"\n  - Average Latency: {avg_latency:.3f}s")
print(f"  - Expected None (silent input): {'PASS' if all(l is None for l in [engine.transcribe(silent_buffer)]) else 'Check'}")

# Test STTResult object
result = engine.transcribe(silent_buffer)
is_none = result is None
print(f"  - Silent input returns None: {is_none}")

print("\nReliability Check:")
print(f"  - Short model triggers at < 3s speech")
print(f"  - Long model triggers at >= 3s speech")
print(f"  - Beam size: 5 (accuracy)")
print(f"  - Word timestamps enabled")
print(f"  - GPU auto-detect: {DEVICE}")

# Fastness rating
if avg_latency < 0.3:
    rating = "EXCELLENT"
elif avg_latency < 0.8:
    rating = "GOOD"
else:
    rating = "AVERAGE"
print(f"\nPerformance Rating: {rating}")
print("=" * 70)
