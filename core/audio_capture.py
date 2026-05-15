"""
audio_capture.py — Microphone input with Voice Activity Detection (VAD)

Uses sounddevice (alternative to PyAudio) for better compatibility with Python 3.12+.
Listens until silence, then returns raw PCM audio bytes.
"""

import io
import wave
import logging
import math
import array
import os
import threading
from collections import deque
import sounddevice as sd
from typing import Optional

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

logger = logging.getLogger(__name__)

# Audio config — must match webrtcvad requirements (10/20/30ms frames)
SAMPLE_RATE = 16000     # Hz
CHANNELS = 1            # mono
SAMPLE_WIDTH = 2        # 16-bit PCM
FRAME_DURATION_MS = 30  # 10, 20, or 30 ms frames for webrtcvad
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # samples per frame

# Silence detection config
SILENCE_THRESHOLD_FRAMES = 12   # ~360ms of silence → stop recording
MAX_RECORDING_FRAMES = 600      # max ~18s of audio
MIN_SPEECH_FRAMES = 2           # ignore sub-60ms noises

# Pre-roll: keep last 180ms of audio before speech is detected
PREROLL_FRAMES = 6
# Ambient noise sampling
NOISE_SAMPLE_FRAMES = 6
ENERGY_THRESHOLD_MULTIPLIER = 1.5
FALLBACK_RMS_THRESHOLD = 250

# Silero VAD config
_VAD_THRESHOLD = float(os.getenv("VAD_THRESHOLD", "0.3"))
PTT_FAST_VAD = os.getenv("PTT_FAST_VAD", "true").strip().lower() not in ("0", "false", "no")


class AudioCapture:
    def __init__(self, vad_aggressiveness: int = 2, energy_callback=None):
        self.webrtc_vad = webrtcvad.Vad(vad_aggressiveness) if webrtcvad else None
        self._silero_vad = None
        self._stop_signal = False
        self._noise_floor: Optional[float] = None
        self._ring = deque(maxlen=PREROLL_FRAMES)
        self._energy_callback = energy_callback
        self._energy_counter = 0
        # Pre-warm Silero VAD in background so first frame isn't delayed
        threading.Thread(target=self._get_silero_vad, daemon=True).start()
        if os.getenv("PREWARM_VAD", "true").strip().lower() not in ("0", "false", "no"):
            threading.Thread(target=self._get_silero_vad, daemon=True).start()

    def _get_silero_vad(self):
        """Lazy-load Silero VAD on first use (ONNX mode, ~2s load once)."""
        if self._silero_vad is None:
            try:
                from silero_vad import load_silero_vad
                self._silero_vad = load_silero_vad(onnx=True)
                logger.info("Silero VAD loaded (ONNX mode).")
            except Exception as e:
                logger.warning(f"Silero VAD failed to load: {e}")
        return self._silero_vad

    def stop(self):
        self._stop_signal = True

    def get_current_energy(self) -> float:
        return self._noise_floor or 0.0

    def get_noise_floor(self) -> float:
        return self._noise_floor or FALLBACK_RMS_THRESHOLD

    def _sample_noise_floor(self, stream) -> float:
        """Sample ambient noise level. Returns the RMS threshold to use."""
        rms_values = []
        for _ in range(NOISE_SAMPLE_FRAMES):
            raw, _ = stream.read(FRAME_SIZE)
            rms = self._rms(bytes(raw))
            if rms > 0:
                rms_values.append(rms)
        if rms_values:
            ambient = sum(rms_values) / len(rms_values)
            threshold = ambient * ENERGY_THRESHOLD_MULTIPLIER
            logger.info(f"Noise floor: {ambient:.0f}, threshold: {threshold:.0f}")
            return threshold
        return FALLBACK_RMS_THRESHOLD

    def _rms(self, raw_pcm: bytes) -> float:
        shorts = array.array('h', raw_pcm)
        if not shorts:
            return 0.0
        sum_sq = sum(float(s) ** 2 for s in shorts)
        return math.sqrt(sum_sq / len(shorts))

    def record_until_silence(self, push_to_talk: bool = False) -> Optional[bytes]:
        self._stop_signal = False
        logger.info(f"Listening for speech (mode={'PTT' if push_to_talk else 'open'})...")

        frames = []
        self._ring.clear()
        silence_count = 0
        speech_started = False
        speech_frame_count = 0
        noise_threshold = FALLBACK_RMS_THRESHOLD

        base_silence = SILENCE_THRESHOLD_FRAMES // 2 if push_to_talk else SILENCE_THRESHOLD_FRAMES
        min_speech = MIN_SPEECH_FRAMES if push_to_talk else 4

        try:
            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SIZE,
                                   device=None, channels=CHANNELS, dtype='int16') as stream:
                # Always sample ambient noise floor first
                noise_threshold = self._sample_noise_floor(stream)
                self._noise_floor = noise_threshold / ENERGY_THRESHOLD_MULTIPLIER

                while True:
                    if self._stop_signal:
                        logger.info("Recording stopped by signal.")
                        break

                    raw, overflowed = stream.read(FRAME_SIZE)
                    raw_bytes = bytes(raw)

                    # Send RMS to HUD every ~90ms for mic visualizer
                    if self._energy_callback:
                        self._energy_counter += 1
                        if self._energy_counter >= 3:
                            self._energy_counter = 0
                            self._energy_callback(self._rms(raw_bytes))

                    # Maintain pre-roll ring buffer (before speech check)
                    self._ring.append(raw_bytes)

                    is_speech = (
                        self._is_speech_fast(raw_bytes, noise_threshold)
                        if push_to_talk and PTT_FAST_VAD
                        else self._is_speech(raw_bytes, noise_threshold)
                    )

                    if is_speech:
                        if not speech_started:
                            # Prepend pre-roll buffer so nothing is clipped
                            frames.extend(list(self._ring))
                            speech_started = True
                        frames.append(raw_bytes)
                        silence_count = 0
                        speech_frame_count += 1
                    elif speech_started:
                        frames.append(raw_bytes)
                        silence_count += 1

                        # Dynamic silence timeout based on speech duration so far
                        elapsed_ms = speech_frame_count * FRAME_DURATION_MS
                        if elapsed_ms < 500:
                            effective_limit = 4          # 120ms for short commands
                        elif elapsed_ms < 2000:
                            effective_limit = base_silence  # normal
                        else:
                            effective_limit = base_silence + 6  # +180ms for long speech

                        if silence_count >= effective_limit:
                            break

                    if len(frames) >= MAX_RECORDING_FRAMES:
                        logger.warning("Max recording duration reached.")
                        break

        except Exception as e:
            logger.error(f"Microphone error: {e}")
            return None

        if speech_frame_count < min_speech:
            logger.info(f"No meaningful speech detected ({speech_frame_count} frames).")
            return None

        logger.info(f"Captured {len(frames)} frames ({len(frames)*FRAME_DURATION_MS}ms)")
        return self._frames_to_wav(frames)

    def _is_speech(self, raw_pcm: bytes, noise_threshold: float = FALLBACK_RMS_THRESHOLD) -> bool:
        # Stage 1: Energy gate (free, sub-ms) — filter silence and low noise
        rms = self._rms(raw_pcm)
        if rms < noise_threshold * 0.5:
            return False

        # Stage 2: Silero VAD (accurate, ~1-5ms) — primary detector
        silero = self._get_silero_vad()
        if silero is not None:
            try:
                import numpy as np
                audio_float = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                if len(audio_float) >= 256:
                    import torch
                    prob = silero(torch.from_numpy(audio_float), 16000).item()
                    return prob > _VAD_THRESHOLD
            except Exception:
                pass

        # Stage 3: webrtcvad fallback (if available)
        if self.webrtc_vad:
            try:
                return self.webrtc_vad.is_speech(raw_pcm, SAMPLE_RATE)
            except Exception:
                pass

        # Stage 4: Energy-only fallback
        return rms > noise_threshold

    def _is_speech_fast(self, raw_pcm: bytes, noise_threshold: float = FALLBACK_RMS_THRESHOLD) -> bool:
        rms = self._rms(raw_pcm)
        # Softer energy gate for PTT
        if rms < noise_threshold * 0.25:
            return False
        if self.webrtc_vad:
            try:
                return self.webrtc_vad.is_speech(raw_pcm, SAMPLE_RATE)
            except Exception:
                pass
        # Use ambient noise floor (not multiplier) for fallback threshold
        floor = self._noise_floor or FALLBACK_RMS_THRESHOLD
        return rms > floor

    def calculate_vibe_urgency(self, wav_bytes: bytes) -> float:
        try:
            rms = self._rms(wav_bytes)
            if rms > 2000:
                return 0.9
            if rms > 1000:
                return 0.5
            return 0.1
        except Exception:
            return 0.0

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def cleanup(self):
        pass
