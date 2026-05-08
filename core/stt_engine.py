"""
stt_engine.py — Whisper.cpp Speech-to-Text

Writes WAV to temp file, calls whisper-cli subprocess, parses stdout.
Target latency: <1s on base.en model with CPU.

Supports any language via WHISPER_LANGUAGE env var:
  - "auto" (default): auto-detect language from audio
  - "en", "hi", "es", "ar", etc.: force specific language
  - Use a multilingual model (ggml-base.bin) for non-English
"""

import os
import time
import logging
import subprocess
import tempfile
from typing import Optional
from dotenv import load_dotenv

# Use all available cores for whisper.cpp — faster on modern CPUs
_CPU_THREADS = str(min(os.cpu_count() or 4, 8))

load_dotenv()
logger = logging.getLogger(__name__)

WHISPER_BIN = os.getenv("WHISPER_BIN", "whisper-cli")
WHISPER_MODEL = os.getenv("WHISPER_MODEL_PATH", "models/ggml-base.bin")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "auto").strip().lower()


class STTEngine:
    def __init__(self):
        self._verify_binary()
        if WHISPER_LANGUAGE == "auto":
            logger.info("STT language: auto-detect (multilingual model recommended)")
        else:
            logger.info(f"STT language: {WHISPER_LANGUAGE}")

    def _verify_binary(self):
        result = subprocess.run(
            [WHISPER_BIN, "--help"],
            capture_output=True,
            timeout=5
        )
        if result.returncode not in (0, 1):  # --help exits 1 on some builds
            raise RuntimeError(
                f"whisper-cli not found at '{WHISPER_BIN}'. "
                "Install whisper.cpp and set WHISPER_BIN in .env"
            )

    def transcribe(self, wav_bytes: bytes) -> Optional[str]:
        """
        Accepts WAV bytes, returns transcribed text string or None.
        """
        start = time.time()

        # Write to temp file (whisper.cpp requires file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp_path = f.name

        try:
            cmd = [
                WHISPER_BIN,
                "-m", WHISPER_MODEL,
                "-f", tmp_path,
                "--no-timestamps",
                "--output-txt",
                "-t", _CPU_THREADS,  # all available cores
            ]

            # Language: "auto" omits the flag (whisper.cpp auto-detects)
            # Any other value (en, hi, es, ar, zh, etc.) pins the language
            if WHISPER_LANGUAGE != "auto":
                cmd.extend(["-l", WHISPER_LANGUAGE])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,             # tighter timeout (was 10s)
            )

            elapsed = time.time() - start
            logger.info(f"STT completed in {elapsed:.2f}s")

            if result.returncode != 0:
                logger.error(f"Whisper error: {result.stderr[:200]}")
                return None

            text = self._parse_output(result.stdout)
            if not text:
                logger.info("Empty transcription returned.")
                return None

            logger.info(f"Transcribed: '{text}'")
            return text

        except subprocess.TimeoutExpired:
            logger.error("Whisper timed out after 8s")
            return None
        finally:
            os.unlink(tmp_path)

    def _parse_output(self, stdout: str) -> str:
        """
        whisper-cli --no-timestamps outputs lines like:
        ' Hello, how are you?' or just the text.
        Strip whitespace and common artifacts.
        """
        lines = [l.strip() for l in stdout.strip().splitlines() if l.strip()]
        text = " ".join(lines)

        # Remove common transcription artifacts
        for artifact in ["[BLANK_AUDIO]", "(Silence)", "[Music]", "[Applause]"]:
            text = text.replace(artifact, "").strip()

        return text


# Fallback: OpenAI Whisper API (when local binary unavailable)
class STTEngineAPI:
    """Use this as fallback during dev if whisper.cpp isn't installed."""

    def __init__(self):
        import openai
        self.client = openai.OpenAI()

    def transcribe(self, wav_bytes: bytes) -> Optional[str]:
        import io
        start = time.time()
        try:
            audio_file = io.BytesIO(wav_bytes)
            audio_file.name = "audio.wav"

            # Use language setting; "auto" → omit language param for auto-detect
            kwargs = {"model": "whisper-1", "file": audio_file}
            if WHISPER_LANGUAGE != "auto":
                kwargs["language"] = WHISPER_LANGUAGE

            result = self.client.audio.transcriptions.create(**kwargs)
            elapsed = time.time() - start
            logger.info(f"API STT completed in {elapsed:.2f}s: '{result.text}'")
            return result.text.strip() or None
        except Exception as e:
            logger.error(f"OpenAI Whisper API error: {e}")
            return None


def get_stt_engine():
    """Returns local engine if available, falls back to API."""
    try:
        return STTEngine()
    except RuntimeError as e:
        logger.warning(f"Local Whisper unavailable ({e}), falling back to API.")
        return STTEngineAPI()
