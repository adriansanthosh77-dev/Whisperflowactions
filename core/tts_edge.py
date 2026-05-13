import os
import asyncio
import logging
import threading
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TTS_VOICE = os.getenv("TTS_VOICE", "en-GB-RyanNeural")


class EdgeTTS:
    """High-quality neural TTS using Microsoft Edge's free API (no API key needed, no downloads)."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop = None
        self._thread: threading.Thread = None
        self._start_loop()

    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

    def speak(self, text: str, on_start_playing=None) -> bool:
        try:
            import edge_tts
            temp_wav = Path("bin/edge_tts/speech.wav")
            temp_wav.parent.mkdir(parents=True, exist_ok=True)

            async def _do_tts():
                communicate = edge_tts.Communicate(text, TTS_VOICE)
                await communicate.save(str(temp_wav))

            future = asyncio.run_coroutine_threadsafe(_do_tts(), self._loop)
            future.result(timeout=30)

            if temp_wav.exists():
                if on_start_playing:
                    on_start_playing()
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Media; "
                    f"$player = New-Object System.Media.SoundPlayer('{temp_wav}'); "
                    f"$player.PlaySync()"
                )
                subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, timeout=30)
                return True
        except Exception as e:
            logger.error(f"Edge TTS failed: {e}")
        return False

    def stop(self):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)


_EDGE_INSTANCE = None

def get_edge_tts() -> EdgeTTS:
    global _EDGE_INSTANCE
    if _EDGE_INSTANCE is None:
        _EDGE_INSTANCE = EdgeTTS()
    return _EDGE_INSTANCE
