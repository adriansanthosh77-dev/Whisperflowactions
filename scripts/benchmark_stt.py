"""
Benchmark: Parakeet vs Whisper STT + Kokoro TTS verification
Uses real Kokoro-generated speech, tests both models on same audio.
"""
import sys, os, time, wave, io, numpy as np
sys.path.insert(0, os.getcwd())
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

print("=" * 60)
print("JARVIS BENCHMARK: STT (Parakeet vs Whisper) + TTS (Kokoro)")
print("=" * 60)

# ── 1. Generate test audio with Kokoro TTS ──
print("\n[1] Generating test speech with Kokoro TTS...")
import sherpa_onnx
kokoro_cfg = sherpa_onnx.OfflineTtsConfig(
    model=sherpa_onnx.OfflineTtsModelConfig(
        kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
            model="models/kokoro-en-v0_19/model.onnx",
            voices="models/kokoro-en-v0_19/voices.bin",
            tokens="models/kokoro-en-v0_19/tokens.txt",
            data_dir="models/kokoro-en-v0_19/espeak-ng-data",
        ),
        num_threads=4,
    ),
)
kokoro = sherpa_onnx.OfflineTts(kokoro_cfg)

phrases = [
    "open youtube", "volume up", "minimize window",
    "what time is it", "open calculator", "close tab",
    "play pause", "check battery", "hello jarvis",
    "take a screenshot", "mute", "new tab",
    "scroll down", "lock pc", "go to sleep",
]

def gen_wav(text):
    r = kokoro.generate(text, sid=0, speed=1.0)
    samples = np.array(r.samples, dtype=np.float64)
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples_int16 = (samples / peak * 0.9 * 32767).astype(np.int16)
    else:
        samples_int16 = np.zeros(len(samples), dtype=np.int16)
    ratio = 16000 / r.sample_rate
    new_len = int(len(samples_int16) * ratio)
    indices = np.linspace(0, len(samples_int16)-1, new_len).astype(np.int32)
    samples_16k = samples_int16[indices]
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(samples_16k.tobytes())
    return buf.getvalue()

# Pre-generate all audio
test_audio = [(p, gen_wav(p)) for p in phrases]
print(f"  Generated {len(test_audio)} audio samples")

# ── 2. Load Parakeet ──
print("\n[2] Loading Parakeet STT (~2 min first time)...")
t0 = time.time()
from core.stt_parakeet import get_parakeet_stt
pk = get_parakeet_stt()
pk_ok = pk and pk._model is not None
print(f"  Parakeet loaded in {time.time()-t0:.0f}s: {'OK' if pk_ok else 'FAIL'}")

# ── 3. Load Whisper ──
print("\n[3] Loading Whisper STT...")
from core.stt_engine import get_stt_engine
whisper = get_stt_engine()
time.sleep(1)  # Let tiny model finish loading
print("  Whisper ready")

# ── 4. Benchmark ──
print("\n[4] Benchmarking...")
print(f"\n  {'Phrase':<25} {'Parakeet':<20} {'Whisper':<20}")
print(f"  {'-'*25} {'-'*20} {'-'*20}")

pk_correct = 0
ws_correct = 0
total = 0

for phrase, wav in test_audio:
    total += 1
    phrase_clean = phrase.lower().strip()

    # Parakeet
    pk_text = None
    if pk_ok:
        try:
            pk_text = pk.transcribe(wav)
        except:
            pass
    pk_clean = pk_text.lower().replace(".","").replace("?","").replace("!","").strip() if pk_text else ""
    pk_match = "OK" if pk_clean == phrase_clean else f"({pk_clean})" if pk_text else "NONE"

    # Whisper
    ws_result = whisper.transcribe(wav)
    ws_text = ws_result.text.lower().replace(".","").replace("?","").replace("!","").strip() if ws_result else ""
    ws_match = "OK" if ws_text == phrase_clean else f"({ws_text})" if ws_result else "NONE"

    if pk_clean == phrase_clean: pk_correct += 1
    if ws_text == phrase_clean: ws_correct += 1

    print(f"  {phrase:<25} {pk_match:<20} {ws_match:<20}")

# ── 5. Kokoro TTS verification ──
print("\n[5] Kokoro TTS verification")
import soundfile as sf  # Use soundfile instead

# Check a generated WAV for proper amplitude
sample_wav = gen_wav("Hello sir. JARVIS is online.")
with wave.open(io.BytesIO(sample_wav), "rb") as wf:
    raw = wf.readframes(wf.getnframes())
    rate = wf.getframerate()
samples = np.frombuffer(raw, dtype=np.int16)
peak = int(np.max(np.abs(samples)))
nonzero = np.count_nonzero(np.abs(samples) > 100)
print(f"  Sample rate: {rate}Hz")
print(f"  Peak amplitude: {peak} (should be > 1000)")
print(f"  Audible samples: {nonzero}/{len(samples)}")
print(f"  TTS: {'OK - audible' if peak > 1000 else 'SILENT!'}")

# ── 6. Results ──
print(f"\n{'='*60}")
print(f"  STT: Parakeet {pk_correct}/{total} | Whisper {ws_correct}/{total}")
print(f"  TTS: Kokoro {'AUDIBLE' if peak > 1000 else 'SILENT'}")
print(f"{'='*60}")
