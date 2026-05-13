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
import sounddevice as sd
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

# Silence detection config (Optimized for speed)
SILENCE_THRESHOLD_FRAMES = 12   # ~360ms of silence → stop recording (was 16)
MAX_RECORDING_FRAMES = 300      # max ~9s of audio
MIN_SPEECH_FRAMES = 2           # ignore sub-60ms noises (was 3)


class AudioCapture:
    def __init__(self, vad_aggressiveness: int = 2):
        self.vad = webrtcvad.Vad(vad_aggressiveness) if webrtcvad else None
        if not self.vad:
            logger.warning("webrtcvad unavailable; using energy-based speech detection.")
        self._stop_signal = False

    def stop(self):
        self._stop_signal = True

    def record_until_silence(self) -> Optional[bytes]:
        self._stop_signal = False
        logger.info("Listening for speech...")

        frames = []
        silence_count = 0
        speech_started = False
        speech_frame_count = 0

        # We'll use a generator to read frames from the input stream
        try:
            with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=FRAME_SIZE, 
                                   device=None, channels=CHANNELS, dtype='int16') as stream:
                while True:
                    if self._stop_signal:
                        logger.info("Recording stopped by signal.")
                        break
                    
                    raw, overflowed = stream.read(FRAME_SIZE)
                    # raw is a buffer/bytes object
                    is_speech = self._is_speech(bytes(raw))

                    if is_speech:
                        frames.append(bytes(raw))
                        speech_started = True
                        silence_count = 0
                        speech_frame_count += 1
                    elif speech_started:
                        frames.append(bytes(raw))
                        silence_count += 1
                        if silence_count >= SILENCE_THRESHOLD_FRAMES:
                            break

                    if len(frames) >= MAX_RECORDING_FRAMES:
                        logger.warning("Max recording duration reached.")
                        break

        except Exception as e:
            logger.error(f"Microphone error: {e}")
            return None

        if speech_frame_count < MIN_SPEECH_FRAMES:
            logger.info("No meaningful speech detected.")
            return None

        logger.info(f"Captured {len(frames)} frames ({len(frames)*FRAME_DURATION_MS}ms)")
        return self._frames_to_wav(frames)

    def _is_speech(self, raw_pcm: bytes) -> bool:
        if not self.vad:
            # Simple RMS energy detection in pure Python
            shorts = array.array('h', raw_pcm)
            if not shorts: return False
            sum_sq = sum(float(s)**2 for s in shorts)
            rms = math.sqrt(sum_sq / len(shorts))
            return rms > 250
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
        # sounddevice doesn't need explicit cleanup like PyAudio
        pass
