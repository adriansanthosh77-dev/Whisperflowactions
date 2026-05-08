"""
audio_capture.py — Microphone input with Voice Activity Detection (VAD)

Listens until silence, then returns raw PCM audio bytes.
Uses webrtcvad to detect speech vs silence (no fixed duration).
"""

import io
import wave
import logging
import pyaudio
import numpy as np
from typing import Optional

try:
    import webrtcvad
except ImportError:
    webrtcvad = None

logger = logging.getLogger(__name__)

# Audio config — must match webrtcvad requirements
SAMPLE_RATE = 16000     # Hz
CHANNELS = 1            # mono
SAMPLE_WIDTH = 2        # 16-bit PCM
FRAME_DURATION_MS = 30  # 10, 20, or 30 ms frames for webrtcvad
FRAME_SIZE = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # samples per frame

# Silence detection config
SILENCE_THRESHOLD_FRAMES = 16   # ~500ms of silence → stop recording (was 900ms)
MAX_RECORDING_FRAMES = 200      # max ~6s of audio (was 9s)
MIN_SPEECH_FRAMES = 3           # ignore sub-90ms noises (was 150ms)


class AudioCapture:
    def __init__(self, vad_aggressiveness: int = 2):
        """
        vad_aggressiveness: 0–3 (3 = most aggressive noise rejection)
        """
        self.vad = webrtcvad.Vad(vad_aggressiveness) if webrtcvad else None
        if not self.vad:
            logger.warning("webrtcvad unavailable; using energy-based speech detection.")
        self._pa = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None

    def _open_stream(self) -> pyaudio.Stream:
        return self._pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=FRAME_SIZE,
        )

    def record_until_silence(self) -> Optional[bytes]:
        """
        Blocks until speech detected, then records until silence.
        Returns WAV bytes or None if nothing captured.
        """
        stream = self._open_stream()
        logger.info("Listening for speech...")

        frames = []
        silence_count = 0
        speech_started = False
        speech_frame_count = 0

        try:
            while True:
                raw = stream.read(FRAME_SIZE, exception_on_overflow=False)
                is_speech = self._is_speech(raw)

                if is_speech:
                    frames.append(raw)
                    speech_started = True
                    silence_count = 0
                    speech_frame_count += 1
                elif speech_started:
                    frames.append(raw)  # include trailing silence in audio
                    silence_count += 1
                    if silence_count >= SILENCE_THRESHOLD_FRAMES:
                        break
                # else: pre-speech silence, ignore

                if len(frames) >= MAX_RECORDING_FRAMES:
                    logger.warning("Max recording duration reached.")
                    break

        finally:
            stream.stop_stream()
            stream.close()

        if speech_frame_count < MIN_SPEECH_FRAMES:
            logger.info("No meaningful speech detected.")
            return None

        logger.info(f"Captured {len(frames)} frames ({len(frames)*FRAME_DURATION_MS}ms)")
        return self._frames_to_wav(frames)

    def _is_speech(self, raw_pcm: bytes) -> bool:
        if not self.vad:
            samples = np.frombuffer(raw_pcm, dtype=np.int16)
            if samples.size == 0:
                return False
            rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
            return rms > 450
        try:
            return self.vad.is_speech(raw_pcm, SAMPLE_RATE)
        except Exception:
            return False

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def cleanup(self):
        self._pa.terminate()
