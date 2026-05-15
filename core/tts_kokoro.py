"""
tts_kokoro.py — Kokoro-82M TTS via sherpa-onnx.
High-quality neural TTS, fully offline, no dependency issues.
Uses sherpa-onnx which bundles espeak-ng phonemizer data.
"""
import os
import wave
import logging
import threading
import numpy as np
import subprocess
from pathlib import Path
import urllib.request
import tarfile

logger = logging.getLogger(__name__)

MODEL_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-en-v0_19.tar.bz2"
MODEL_DIR = Path("models/kokoro-en-v0_19")


class KokoroTTS:
    def __init__(self):
        self._tts = None
        self._ensure_model()
        self._load_model()

    def _ensure_model(self):
        if MODEL_DIR.exists():
            logger.info("Kokoro model found locally.")
            return
        logger.info("Downloading Kokoro TTS model (326MB)...")
        import requests
        os.makedirs(MODEL_DIR, exist_ok=True)
        archive = MODEL_DIR.parent / (MODEL_DIR.name + ".tar.bz2")
        resp = requests.get(MODEL_URL, stream=True, timeout=600)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        with open(archive, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total and downloaded % (1024 * 1024) == 0:
                    logger.info(f"  Downloaded {downloaded // (1024*1024)}/{total // (1024*1024)} MB")
        logger.info("Extracting model...")
        with tarfile.open(archive, "r:bz2") as tar:
            tar.extractall(path=MODEL_DIR.parent)
        archive.unlink()
        logger.info("Kokoro model ready.")

    def _load_model(self):
        try:
            import sherpa_onnx
            config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    kokoro=sherpa_onnx.OfflineTtsKokoroModelConfig(
                        model=str(MODEL_DIR / "model.onnx"),
                        voices=str(MODEL_DIR / "voices.bin"),
                        tokens=str(MODEL_DIR / "tokens.txt"),
                        data_dir=str(MODEL_DIR / "espeak-ng-data"),
                    ),
                    num_threads=os.cpu_count() or 4,
                ),
            )
            self._tts = sherpa_onnx.OfflineTts(config)
            logger.info("Kokoro TTS ready (sherpa-onnx).")
            # Build cache in background, well after boot — let first commands run fast
            def _delayed_cache():
                import time
                time.sleep(30)  # Wait 30s so first user commands aren't competing with cache
                _build_cache(self)
            threading.Thread(target=_delayed_cache, daemon=True).start()
        except Exception as e:
            logger.error(f"Kokoro load failed: {e}")
            self._tts = None

    def speak(self, text: str, speed: float = 1.2, on_start=None, on_end=None) -> bool:
        if not self._tts:
            return False
        temp_wav = Path("bin/kokoro/speech.wav")
        temp_wav.parent.mkdir(parents=True, exist_ok=True)

        # Check pre-cache first — instant playback, no generation
        if play_cached(text, temp_wav, on_start, on_end):
            return True
        # Check if text starts with a cached phrase
        for phrase in _CACHED_PHRASES:
            if text.startswith(phrase) and phrase in _TTS_CACHE:
                if play_cached(phrase, temp_wav, on_start, on_end):
                    return True

        try:
            result = self._tts.generate(text, sid=0, speed=speed)
            samples = np.array(result.samples, dtype=np.float64)
            samples = (samples * 32767).astype(np.int16)
            if len(samples) == 0:
                return False
            temp_wav.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(temp_wav), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(result.sample_rate)
                wf.writeframes(samples.tobytes())
            if temp_wav.exists():
                try:
                    import winsound
                    if on_start:
                        on_start()
                    winsound.PlaySound(str(temp_wav), winsound.SND_FILENAME)
                    if on_end:
                        on_end()
                    return True
                except Exception:
                    pass
                # Fallback: PowerShell System.Media
                try:
                    if on_start:
                        on_start()
                    ps_cmd = (
                        f"Add-Type -AssemblyName System.Media; "
                        f"$player = New-Object System.Media.SoundPlayer('{temp_wav}'); "
                        f"$player.PlaySync()"
                    )
                    subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=30)
                    if on_end:
                        on_end()
                    return True
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Kokoro speak error: {e}")
        return False


_KOKORO_INSTANCE = None

# ── TTS Pre-cache for instant common responses ──
_TTS_CACHE: dict[str, tuple] = {}
_CACHED_PHRASES = [
    "Executing",
    "Done",
    "All tasks completed",
    "I didn't catch that",
    "Could you repeat it?",
    "Task aborted",
    "Cancelled",
    "Listening",
    "One moment",
]


def _build_cache(kokoro):
    """Pre-generate common TTS responses at boot so they play instantly."""
    if not kokoro or not kokoro._tts:
        return
    import time
    t0 = time.time()
    for phrase in _CACHED_PHRASES:
        try:
            result = kokoro._tts.generate(phrase, sid=0, speed=1.2)
            if result and len(result.samples) > 0:
                _TTS_CACHE[phrase] = (np.array(result.samples, dtype=np.float64),
                                      result.sample_rate)
        except Exception:
            pass
    logger.info(f"TTS cache: {len(_TTS_CACHE)}/{len(_CACHED_PHRASES)} phrases cached in {time.time()-t0:.1f}s")


def play_cached(phrase: str, temp_wav: Path, on_start=None, on_end=None) -> bool:
    """Play a pre-cached phrase instantly without generation."""
    entry = _TTS_CACHE.get(phrase)
    if entry is None:
        return False
    samples, sr = entry
    samples_int = (samples * 32767).astype(np.int16)
    with wave.open(str(temp_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples_int.tobytes())
    try:
        import winsound
        if on_start:
            on_start()
        winsound.PlaySound(str(temp_wav), winsound.SND_FILENAME)
        if on_end:
            on_end()
        return True
    except Exception:
        return False


def get_kokoro_tts() -> KokoroTTS:
    global _KOKORO_INSTANCE
    if _KOKORO_INSTANCE is None:
        _KOKORO_INSTANCE = KokoroTTS()
    return _KOKORO_INSTANCE
