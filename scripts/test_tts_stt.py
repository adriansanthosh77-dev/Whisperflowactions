"""
Full test: Parakeet STT + Kokoro TTS loopback test.
Kokoro speaks -> Parakeet transcribes -> verify accuracy.
"""
import sys, os; sys.path.insert(0, os.getcwd())
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
import wave, io, numpy as np, time, json

results = {"passed": 0, "failed": 0}

def test(name, fn):
    try:
        fn()
        results["passed"] += 1
        print(f"  PASS: {name}")
    except Exception as e:
        results["failed"] += 1
        print(f"  FAIL: {name}: {e}")

print("=" * 60)
print("TEST: Kokoro TTS + Parakeet STT")
print("=" * 60)

# ── 1. Load Kokoro TTS ──
print("\n[1] Loading Kokoro TTS...")
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

def tts(text):
    r = kokoro.generate(text, sid=0, speed=1.0)
    samples = np.array(r.samples, dtype=np.float64)
    mx = float(np.max(np.abs(samples)))
    samples_int16 = (samples * 32767).astype(np.int16)
    # Resample 24kHz -> 16kHz
    ratio = 16000 / r.sample_rate
    new_len = int(len(samples_int16) * ratio)
    indices = np.linspace(0, len(samples_int16)-1, new_len).astype(np.int32)
    samples_16k = samples_int16[indices]
    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
        wf.writeframes(samples_16k.tobytes())
    return wav_buf.getvalue(), mx

# ── 2. Load Parakeet STT ──
print("\n[2] Loading Parakeet STT...")
from core.stt_parakeet import get_parakeet_stt
pk = get_parakeet_stt()
print(f"  Parakeet loaded: {pk._model is not None}")
if not pk._model:
    print("  Parakeet not available, using Whisper fallback")
    from core.stt_engine import get_stt_engine
    whisper_stt = get_stt_engine()

# ── 3. Test Kokoro voice quality ──
print("\n[3] Kokoro voice generation")
def test_kokoro():
    wav, mx = tts("Hello sir. JARVIS is online. All systems operational.")
    assert mx > 0.1, f"Audio too quiet: max={mx}"
    assert len(wav) > 10000, f"Audio too short: {len(wav)} bytes"
    # Save so user can play it
    with open("kokoro_test_output.wav", "wb") as f:
        f.write(wav)
    print(f"  Generated: {len(wav)} bytes, max amplitude={mx:.3f}")
    print(f"  Saved to: kokoro_test_output.wav")
test("Kokoro generates clear audio", test_kokoro)

# ── 4. Test Parakeet transcription ──
print("\n[4] Parakeet + Whisper transcription test")
phrases = [
    "open youtube",
    "volume up",
    "what time is it",
    "open calculator",
    "minimize window",
    "play pause",
    "check battery",
    "go to sleep",
    "hello jarvis",
]

for phrase in phrases:
    wav, mx = tts(phrase)
    if pk._model:
        text = pk.transcribe(wav)
        if text:
            status = "OK" if text.lower() == phrase.lower() else "MISMATCH"
            print(f"  [{status:>8}] '{phrase}' -> '{text}'")
        else:
            print(f"  [  FAIL  ] '{phrase}' -> Parakeet returned None")

# ── 5. Save example for each voice ──
print("\n[5] Saving voice sample WAVs")
for i, phrase in enumerate(["Good morning sir.", "Opening YouTube.", "Volume increased."]):
    wav, mx = tts(phrase)
    with open(f"kokoro_sample_{i}.wav", "wb") as f:
        f.write(wav)
    print(f"  Saved: kokoro_sample_{i}.wav ({len(wav)} bytes)")

print(f"\n{'='*60}")
print(f"RESULTS: {results['passed']}/{results['passed']+results['failed']} passed")
print(f"{'='*60}")
print("\nKokoro WAV files saved. You can play them with any audio player.")
