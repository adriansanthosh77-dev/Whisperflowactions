import os
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)


class SileroVAD:
    """
    Neural Voice Activity Detection using Silero VAD (PyTorch).
    Uses get_speech_timestamps for reliable speech detection.
    Falls back to energy-based VAD if PyTorch model is unavailable.
    """
    def __init__(self, threshold: float = 0.15):
        self.threshold = threshold
        self._model = None
        self._init_model()

    def _init_model(self):
        try:
            import silero_vad
            self._model = silero_vad.load_silero_vad()
            logger.info("Silero VAD loaded (PyTorch).")
        except Exception as e:
            logger.warning(f"Silero VAD not available ({e}), using energy fallback.")
            self._model = None

    def reset_states(self):
        pass

    def is_speech(self, audio_bytes: bytes, sample_rate: int = 16000) -> bool:
        if self._model is None:
            return self._energy_vad(audio_bytes)

        try:
            import silero_vad
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            ts = silero_vad.get_speech_timestamps(
                audio_float32,
                self._model,
                sampling_rate=sample_rate,
                threshold=self.threshold,
            )
            return len(ts) > 0

        except Exception as e:
            logger.error(f"VAD error: {e}")
            return self._energy_vad(audio_bytes)

    def _energy_vad(self, audio_bytes: bytes) -> bool:
        audio = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        return rms > 500.0


_VAD_INSTANCE = None

def get_silero_vad() -> SileroVAD:
    global _VAD_INSTANCE
    if _VAD_INSTANCE is None:
        _VAD_INSTANCE = SileroVAD()
    return _VAD_INSTANCE
