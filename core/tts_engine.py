"""
tts_engine.py — JARVIS Voice Feedback System.

Providers (in priority order):
  1. edge (default) — Microsoft Edge free neural TTS via edge-tts
  2. piper — Local ONNX neural TTS (fallback if edge fails)
  3. powershell — Native Windows Speech API (last resort)
"""
import os
import threading
import logging
import subprocess

logger = logging.getLogger(__name__)

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge").strip().lower()


class TTSEngine:
    def __init__(self):
        self.provider = TTS_PROVIDER
        self._edge = None

    def say(self, text: str, wait: bool = False, on_start=None, on_end=None):
        if not text: return

        def _wrapper(target_func):
            try:
                target_func(text, on_start)
            finally:
                if on_end: on_end()

        if self.provider in ("edge", "kokoro"):
            t = threading.Thread(target=_wrapper, args=(self._speak_edge,), daemon=True)
            t.start()
            if wait: t.join()
        elif self.provider == "piper":
            t = threading.Thread(target=_wrapper, args=(self._speak_piper,), daemon=True)
            t.start()
            if wait: t.join()
        else:
            t = threading.Thread(target=_wrapper, args=(self._speak_powershell,), daemon=True)
            t.start()
            if wait: t.join()

    def _speak_edge(self, text: str, on_start_playing=None):
        """High-quality neural TTS via Microsoft Edge free API."""
        try:
            from core.tts_edge import get_edge_tts
            edge = get_edge_tts()
            if not edge.speak(text, on_start_playing=on_start_playing):
                self._speak_powershell(text, on_start_playing)
        except ImportError:
            self._speak_piper(text, on_start_playing)
        except Exception as e:
            logger.error(f"Edge TTS failed: {e}")
            self._speak_piper(text, on_start_playing)

    def _speak_piper(self, text: str, on_start_playing=None):
        """Neural local TTS using Piper (fallback)."""
        try:
            from core.tts_piper import get_piper_tts
            piper = get_piper_tts()
            if not piper.speak(text, on_start_playing=on_start_playing):
                self._speak_powershell(text, on_start_playing)
        except Exception as e:
            logger.error(f"Piper speak failed: {e}")
            self._speak_powershell(text, on_start_playing)

    def _speak_powershell(self, text: str, on_start_playing=None):
        """Native Windows Speech fallback via PowerShell."""
        try:
            if on_start_playing: on_start_playing()
            safe_text = text.replace("'", "''")
            ps_command = (
                f"Add-Type -AssemblyName System.Speech; "
                f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe_text}')"
            )
            subprocess.run(["powershell", "-Command", ps_command], capture_output=True, timeout=15)
        except Exception as e:
            logger.error(f"PowerShell TTS failed: {e}")


def get_tts_engine():
    return TTSEngine()
