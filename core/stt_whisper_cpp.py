"""
stt_whisper_cpp.py — whisper.cpp CLI wrapper.
Loads the model via OS file cache (~8ms per 0.5s audio).
Used as primary for short speech (<1.5s) — faster than faster-whisper's 50ms.
"""
import subprocess
import os
import tempfile
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CLI = Path("whisper-cli.exe")
_MODEL = Path("models/ggml-tiny.en.bin")


def transcribe(wav_bytes: bytes) -> Optional[tuple[str, float]]:
    """Transcribe audio via whisper.cpp CLI.
    Returns (text, confidence) or None.
    ~8ms for 0.5s audio, ~50ms for 5s audio.
    """
    if not _CLI.exists() or not _MODEL.exists():
        return None

    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav_bytes)
            tmp = f.name

        result = subprocess.run(
            [str(_CLI), "-m", str(_MODEL), tmp, "-otxt", "-nt",
             "-t", str(os.cpu_count() or 4), "-l", "en", "-bo", "1"],
            capture_output=True, text=True, timeout=10,
        )
        text = result.stdout.strip()
        if not text:
            return None

        # Estimate confidence from stderr (whisper prints logprob info there)
        confidence = 0.8  # default for whisper.cpp
        for line in (result.stderr or "").splitlines():
            if "prob" in line.lower():
                try:
                    prob = float(line.split()[-1].strip(")").strip())
                    if 0 < prob <= 1:
                        confidence = prob
                        break
                except:
                    pass

        return text, confidence

    except subprocess.TimeoutExpired:
        logger.warning("whisper.cpp timed out")
        return None
    except Exception as e:
        logger.warning(f"whisper.cpp error: {e}")
        return None
    finally:
        try:
            os.unlink(tmp)
        except:
            pass


def available() -> bool:
    return _CLI.exists() and _MODEL.exists()
