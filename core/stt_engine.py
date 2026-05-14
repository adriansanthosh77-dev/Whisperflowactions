"""
stt_engine.py — Dual-model STT for speed + accuracy

Short speech (<3s, reflexes): tiny.en for fast execution
Long speech (>3s, dictation): medium/large quantized for word-perfect accuracy
"""

import os
import time
import logging
import threading
import io
import wave
import numpy as np
from typing import Optional
from faster_whisper import WhisperModel

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

logger = logging.getLogger(__name__)


def get_hardware_config():
    cpu_count = os.cpu_count() or 4
    threads = int(os.getenv("STT_THREADS", cpu_count))
    device = "cpu"
    compute_type = "int8"

    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
            logger.info("GPU: CUDA detected")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
            compute_type = "float16"
            logger.info("GPU: MPS detected")
    except ImportError:
        pass

    return device, compute_type, threads


DEVICE, COMPUTE_TYPE, THREADS = get_hardware_config()

STT_PROVIDER = os.getenv("STT_PROVIDER", "whisper").strip().lower()
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en").strip().lower()
STT_MODEL_SHORT = os.getenv("STT_MODEL_SHORT", "base.en").strip()
STT_MODEL_LONG = os.getenv("STT_MODEL_LONG", "medium.en").strip()
LONG_PHRASE_THRESHOLD = float(os.getenv("STT_LONG_THRESHOLD", "2.0"))
LOW_CONF_THRESHOLD = float(os.getenv("STT_LOW_CONF_THRESHOLD", "0.6"))

REFLEX_PROMPTS = (
    "JARVIS, assistant, computer, hello, hi, thanks, thank you, open, close, "
    "search for, navigate to, type, press, notepad, browser, chrome, vscode, "
    "terminal, screenshot, volume, brightness, summarize, explain, "
    "what is, tell me about, teach me, help, "
    "start dictation, stop dictation, go to sleep, wake up"
)

HALLUCINATION_PATTERNS = [
    r"\[.*?\]",
    r"\(.*?\)",
    "Thanks for watching",
    "Please subscribe",
    r"\byou,\s*you(?:,\s*you)*\b",
]


class STTResult:
    def __init__(self, text: str, words: list, confidence: float,
                 low_confidence: bool, low_conf_words: list,
                 model_used: str, duration: float):
        self.text = text
        self.words = words
        self.confidence = confidence
        self.low_confidence = low_confidence
        self.low_conf_words = low_conf_words
        self.model_used = model_used
        self.duration = duration

    def __bool__(self):
        return bool(self.text)

    def __str__(self):
        return self.text


class STTEngine:
    _tiny_model = None
    _large_model = None
    _tiny_lock = threading.Lock()
    _large_lock = threading.Lock()
    _large_ready = threading.Event()

    def __init__(self):
        threading.Thread(target=self._load_tiny, daemon=True).start()
        if STT_PROVIDER == "whisper":
            threading.Thread(target=self._warm_large, daemon=True).start()
        logger.info(
            f"STT: short={STT_MODEL_SHORT}, long={STT_MODEL_LONG}, "
            f"threshold={LONG_PHRASE_THRESHOLD}s, "
            f"{THREADS} threads, {DEVICE}/{COMPUTE_TYPE}"
        )

    def _load_tiny(self):
        if STTEngine._tiny_model is not None:
            return
        with STTEngine._tiny_lock:
            if STTEngine._tiny_model is None:
                logger.info(f"Loading short model: {STT_MODEL_SHORT}")
                STTEngine._tiny_model = WhisperModel(
                    STT_MODEL_SHORT,
                    device=DEVICE,
                    compute_type=COMPUTE_TYPE,
                    cpu_threads=THREADS,
                    download_root="models",
                )
                logger.info(f"Short model ready: {STT_MODEL_SHORT}")

    def _warm_large(self):
        """Background warm-up of large model — never blocks tiny model.
        Only loads if model is already downloaded locally."""
        import os as _os
        model_dir = _os.path.join("models", f"models--Systran--faster-whisper-{STT_MODEL_LONG}")
        snapshots = _os.path.join(model_dir, "snapshots")
        has_files = _os.path.isdir(snapshots)
        if has_files:
            found = False
            for entry in _os.listdir(snapshots):
                ep = _os.path.join(snapshots, entry)
                if _os.path.isdir(ep) and len([f for f in _os.listdir(ep) if f.endswith(".bin")]) >= 2:
                    found = True
                    break
            has_files = found
        if not has_files:
            logger.info(f"Long model {STT_MODEL_LONG} not cached locally, skipping warm-up (will load on demand)")
            STTEngine._large_ready.set()
            return
        try:
            logger.info(f"Warming long model: {STT_MODEL_LONG} (background)")
            if STTEngine._large_model is None:
                with STTEngine._large_lock:
                    if STTEngine._large_model is None:
                        STTEngine._large_model = WhisperModel(
                            STT_MODEL_LONG,
                            device=DEVICE,
                            compute_type=COMPUTE_TYPE,
                            cpu_threads=THREADS,
                            download_root="models",
                        )
            logger.info(f"Long model ready: {STT_MODEL_LONG}")
        except Exception as e:
            logger.warning(f"Long model warm-up failed, using short only: {e}")
        finally:
            STTEngine._large_ready.set()

    def _get_tiny(self):
        if STTEngine._tiny_model is None:
            self._load_tiny()
        return STTEngine._tiny_model

    def _get_large(self):
        if STTEngine._large_model is None:
            STTEngine._large_ready.wait(timeout=60)
        return STTEngine._large_model

    def _audio_duration(self, wav_bytes: bytes) -> float:
        try:
            if wav_bytes[:4] == b"RIFF":
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    return frames / rate if rate > 0 else 0.0
        except Exception:
            pass
        return 0.0

    def transcribe(self, wav_bytes: bytes, on_segment: callable = None) -> Optional[STTResult]:
        start = time.time()
        if not wav_bytes:
            return None

        audio = self._decode_audio(wav_bytes)
        if audio is None or audio.size == 0:
            return None

        duration = self._audio_duration(wav_bytes)

        # Parakeet fast path (experimental, falls back to Whisper)
        if STT_PROVIDER == "parakeet":
            try:
                from core.stt_parakeet import get_parakeet_stt
                pk = get_parakeet_stt()
                if pk and pk._model:
                    text = pk.transcribe(wav_bytes)
                    if text:
                        elapsed = time.time() - start
                        logger.info(f"Parakeet: '{text[:60]}' in {elapsed:.2f}s")
                        return STTResult(text=text, words=[], confidence=0.95,
                                         low_confidence=False, low_conf_words=[],
                                         model_used="parakeet", duration=elapsed)
            except Exception:
                pass
            logger.info("Parakeet unavailable, using Whisper")

        is_long = duration > LONG_PHRASE_THRESHOLD

        if is_long:
            model = self._get_large()
            model_name = STT_MODEL_LONG
            prompt = None
            silence_ms = 1500
        else:
            model = self._get_tiny()
            model_name = STT_MODEL_SHORT
            prompt = REFLEX_PROMPTS
            silence_ms = 500

        if model is None:
            model = self._get_tiny()
            model_name = STT_MODEL_SHORT
            prompt = REFLEX_PROMPTS
            silence_ms = 500

        try:
            segments, info = model.transcribe(
                audio,
                beam_size=5,
                language=WHISPER_LANGUAGE if WHISPER_LANGUAGE != "auto" else None,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.5,
                    min_speech_duration_ms=100,
                    min_silence_duration_ms=silence_ms,
                ),
                initial_prompt=prompt,
                word_timestamps=True,
            )

            text_parts = []
            all_words = []
            total_prob = 0.0
            word_count = 0

            for segment in segments:
                text_parts.append(segment.text)
                if on_segment:
                    on_segment(segment.text)
                if segment.words:
                    for w in segment.words:
                        prob = getattr(w, "probability", 1.0)
                        all_words.append({"word": w.word, "probability": prob})
                        total_prob += prob
                        word_count += 1

            raw_text = " ".join(text_parts).strip()
            if not raw_text:
                return None

            cleaned = self._clean_text(raw_text)
            avg_conf = total_prob / word_count if word_count > 0 else 1.0
            low_words = [w for w in all_words if w["probability"] < LOW_CONF_THRESHOLD]

            elapsed = time.time() - start
            logger.info(
                f"STT ({model_name}): '{cleaned}' "
                f"(dur={duration:.1f}s, conf={avg_conf:.2f}, "
                f"low={len(low_words)} words, {elapsed:.2f}s)"
            )

            return STTResult(
                text=cleaned,
                words=all_words,
                confidence=avg_conf,
                low_confidence=len(low_words) > 0,
                low_conf_words=low_words,
                model_used=model_name,
                duration=duration,
            )

        except Exception as e:
            logger.error(f"STT error: {e}")
            return None

    def _decode_audio(self, wav_bytes: bytes) -> Optional[np.ndarray]:
        try:
            if wav_bytes[:4] == b"RIFF":
                with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                    channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    frames = wf.readframes(wf.getnframes())
                if sample_width != 2:
                    logger.error(f"Unsupported sample width: {sample_width}")
                    return None
                audio = np.frombuffer(frames, dtype=np.int16)
                if channels > 1:
                    audio = audio.reshape(-1, channels).mean(axis=1).astype(np.int16)
            else:
                audio = np.frombuffer(wav_bytes, dtype=np.int16)
            return audio.astype(np.float32) / 32768.0
        except Exception as e:
            logger.error(f"Audio decode failed: {e}")
            return None

    def _clean_text(self, text: str) -> str:
        import re
        for pattern in HALLUCINATION_PATTERNS:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)
        text = re.sub(r"([,.!?])\1+", r"\1", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()


def get_stt_engine():
    return STTEngine()
