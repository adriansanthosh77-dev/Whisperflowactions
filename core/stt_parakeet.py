"""
stt_parakeet.py — NVIDIA Parakeet TDT 0.6B v3 via onnx-asr.
Uses INT8 model for faster loading (~25s vs ~120s for FP32).
"""
import os
import re
import io
import wave
import math
import time
import logging
import threading
import numpy as np
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"
_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"
_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{_REPO.replace('/', '--')}"


def check_parakeet_health() -> tuple[bool, str]:
    """Check if the Parakeet model files and onnx_asr are available."""
    # First check if the Python package is installed
    try:
        import onnx_asr
    except ImportError:
        return False, "onnx_asr package not installed (pip install onnx-asr)"

    # Check model files in huggingface cache
    expected_files = [
        "config.json",
        "encoder-model.onnx",
        "decoder_joint-model.onnx",
    ]
    snapshots_dir = _CACHE / "snapshots"
    if not snapshots_dir.exists():
        return False, f"Parakeet model not cached (no snapshots dir at {snapshots_dir})"
    try:
        for entry in snapshots_dir.iterdir():
            if entry.is_dir():
                present = [f for f in expected_files if (entry / f).exists()]
                if len(present) == len(expected_files):
                    return True, f"Parakeet ready ({len(present)}/{len(expected_files)} files)"
        return False, f"Parakeet cached but incomplete ({len(present) if 'present' in dir() else 0}/{len(expected_files)} files)"
    except Exception as e:
        return False, f"Parakeet health check failed: {e}"


def preprocess_audio(wav_bytes: bytes, target_rms: float = 0.15) -> bytes:
    """Apply light preprocessing: normalize RMS level and trim DC offset.
    Operates on normalized float samples internally to avoid int16 truncation.
    Returns preprocessed WAV bytes (same format in/out).
    """
    try:
        if wav_bytes[:4] != b"RIFF":
            return wav_bytes

        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            params = wf.getparams()
            raw = wf.readframes(wf.getnframes())

        # Convert to normalized float [-1, 1]
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        # Remove DC offset
        dc = np.mean(samples)
        samples -= dc

        # RMS normalization (now in float range)
        rms = math.sqrt(np.mean(samples ** 2))
        if rms > 0.001:
            gain = target_rms / rms
            samples = np.clip(samples * gain, -1.0, 1.0)

        # Convert back to int16
        samples_int = (samples * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf_out:
            wf_out.setparams(params)
            wf_out.writeframes(samples_int.tobytes())
        return buf.getvalue()
    except Exception as e:
        logger.warning(f"Audio preprocessing failed (using original): {e}")
        return wav_bytes


def trim_silence(wav_bytes: bytes, threshold: float = 0.01, frame_ms: int = 10) -> tuple[bytes, float]:
    """Remove leading/trailing silence from a WAV.
    Returns (trimmed_wav_bytes, speech_duration_seconds).
    Returns original wav_bytes if all silence or on error.
    """
    if not wav_bytes or wav_bytes[:4] != b"RIFF":
        return wav_bytes, 0.0
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        frame_len = int(sr * frame_ms / 1000)
        if len(samples) < frame_len:
            return wav_bytes, round(len(samples) / sr, 3)

        n_frames = len(samples) // frame_len
        frames = samples[:n_frames * frame_len].reshape(-1, frame_len)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))

        above = np.where(rms > threshold)[0]
        if len(above) == 0:
            return wav_bytes, 0.0

        start = above[0] * frame_len
        end = min((above[-1] + 1) * frame_len, len(samples))
        trimmed = samples[start:end]
        speech_dur = round(len(trimmed) / sr, 3)

        trimmed_int16 = (trimmed * 32767.0).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf_out:
            wf_out.setnchannels(1)
            wf_out.setsampwidth(2)
            wf_out.setframerate(sr)
            wf_out.writeframes(trimmed_int16.tobytes())
        return buf.getvalue(), speech_dur
    except Exception as e:
        logger.warning(f"trim_silence failed: {e}")
        return wav_bytes, 0.0


def estimate_confidence(text: str, audio_duration: float) -> float:
    """Heuristic confidence estimate for Parakeet output.
    Returns 0.0-1.0 based on text length, speaking rate, and character distribution.
    """
    if not text or audio_duration <= 0:
        return 0.0

    words = text.split()
    word_count = len(words)
    char_count = len(text)

    if word_count == 0:
        return 0.0

    # Penalize very short output relative to audio duration
    words_per_second = word_count / audio_duration
    if words_per_second < 0.5:
        # Way too few words for the duration
        rate_score = max(0.0, words_per_second / 2.0)
    elif words_per_second > 6.0:
        # Suspiciously fast speaking
        rate_score = max(0.0, 1.0 - (words_per_second - 6.0) / 4.0)
    else:
        rate_score = 1.0

    # Penalize unusually short texts
    length_score = min(1.0, char_count / 20.0) if char_count < 20 else 1.0

    # Penalize all-uppercase or all-lowercase (could be hallucination)
    upper_ratio = sum(1 for c in text if c.isupper()) / max(char_count, 1)
    case_score = 1.0
    if upper_ratio > 0.8 and word_count > 1:
        case_score = 0.7
    elif upper_ratio == 0 and word_count > 1:
        case_score = 0.9

    # Penalize repetitive patterns (hallucination marker)
    unique_chars = len(set(text.lower()))
    diversity = unique_chars / max(char_count, 1)
    diversity_score = min(1.0, diversity * 5.0)

    confidence = rate_score * 0.4 + length_score * 0.2 + case_score * 0.2 + diversity_score * 0.2
    return round(min(1.0, max(0.1, confidence)), 3)


class ParakeetSTT:
    def __init__(self, lazy: bool = False):
        self._model = None
        self._load_error: Optional[str] = None
        self._load_event = threading.Event()
        if not lazy:
            self._load_model()

    def _load_model(self):
        """Load the Parakeet ONNX model. Can block up to ~30s."""
        try:
            import onnx_asr
            logger.info(f"Loading Parakeet TDT ({MODEL_NAME})...")
            # Use CPU provider explicitly (DML can cause hangs with this model)
            self._model = onnx_asr.load_model(
                MODEL_NAME,
                providers=["CPUExecutionProvider"],
            )
            logger.info("Parakeet TDT loaded.")
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Parakeet load failed: {e}")
            self._model = None
        finally:
            self._load_event.set()

    def wait_until_ready(self, timeout: float = 60.0) -> bool:
        """Block until model is loaded. Returns True if ready."""
        if self._model is not None:
            return True
        if self._load_error:
            return False
        ready = self._load_event.wait(timeout=timeout)
        if ready and self._model is not None:
            return True
        return False

    def is_loaded(self) -> bool:
        return self._model is not None

    def health(self) -> tuple[bool, str]:
        if self._model is not None:
            return True, "Parakeet model loaded"
        if self._load_error:
            return False, f"Parakeet load failed: {self._load_error}"
        return False, "Parakeet model not yet loaded"

    def transcribe(self, wav_bytes: bytes, audio_duration: float = 0.0) -> Optional[tuple[str, float]]:
        """Transcribe audio. Returns (text, confidence) or None."""
        if not self._model:
            return None

        try:
            if wav_bytes[:4] == b"RIFF":
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    raw = wf.readframes(wf.getnframes())
                    sr = wf.getframerate()
            else:
                raw = wav_bytes
                sr = 16000

            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            text = self._model.recognize(audio, sample_rate=sr)

            if not text:
                return None

            text = re.sub(r'<[^>]+>', '', text).strip()
            if not text:
                return None

            # Estimate duration from audio if not provided
            if audio_duration <= 0 and wav_bytes[:4] == b"RIFF":
                try:
                    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                        audio_duration = wf.getnframes() / max(wf.getframerate(), 1)
                except Exception:
                    audio_duration = 0.0

            confidence = estimate_confidence(text, audio_duration)
            return text, confidence

        except Exception as e:
            logger.error(f"Parakeet transcribe error: {e}")
            return None


_PARASKEET_INSTANCE = None
_PARASKEET_LOCK = threading.Lock()


def get_parakeet_stt(lazy: bool = False) -> ParakeetSTT:
    global _PARASKEET_INSTANCE
    if _PARASKEET_INSTANCE is None:
        with _PARASKEET_LOCK:
            if _PARASKEET_INSTANCE is None:
                _PARASKEET_INSTANCE = ParakeetSTT(lazy=lazy)
    return _PARASKEET_INSTANCE
