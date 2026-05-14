"""
stt_parakeet.py — NVIDIA Parakeet TDT 0.6B v3 via onnx-asr.
Uses INT8 model for faster loading (~25s vs ~120s for FP32).
"""
import os
import re
import io
import wave
import logging
import numpy as np
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Use istupakov's ONNX model via onnx-asr
MODEL_NAME = "nemo-parakeet-tdt-0.6b-v3"
# The INT8 model files from huggingface cache
_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"
_CACHE = Path.home() / ".cache" / "huggingface" / "hub" / f"models--{_REPO.replace('/', '--')}"


class ParakeetSTT:
    def __init__(self):
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            import onnx_asr
            logger.info(f"Loading Parakeet TDT ({MODEL_NAME})...")
            self._model = onnx_asr.load_model(MODEL_NAME)
            logger.info("Parakeet TDT loaded.")
        except Exception as e:
            logger.error(f"Parakeet load failed: {e}")
            self._model = None

    def transcribe(self, wav_bytes: bytes) -> Optional[str]:
        if not self._model:
            return None
        try:
            # Fast path: skip WAV header parsing for PCM data
            if wav_bytes[:4] == b"RIFF":
                import wave
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    raw = wf.readframes(wf.getnframes())
            else:
                raw = wav_bytes  # Assume raw PCM
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            text = self._model.recognize(audio)
            if not text:
                return None
            text = re.sub(r'<[^>]+>', '', text).strip()
            return text if text else None
        except Exception as e:
            logger.error(f"Parakeet error: {e}")
            return None


_PARASKEET_INSTANCE = None

def get_parakeet_stt() -> ParakeetSTT:
    global _PARASKEET_INSTANCE
    if _PARASKEET_INSTANCE is None:
        _PARASKEET_INSTANCE = ParakeetSTT()
    return _PARASKEET_INSTANCE
