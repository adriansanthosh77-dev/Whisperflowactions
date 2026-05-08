"""
tts_engine.py — JARVIS Voice Feedback System.

Supports:
1. Local (pyttsx3): Zero latency, offline, robotic but fast.
2. OpenAI (TTS-1): Premium, human-like, requires API key and internet.
"""

import os
import threading
import logging
import pyttsx3
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "local").strip().lower()
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "").strip() # Optional specific voice

class TTSEngine:
    def __init__(self):
        self.provider = TTS_PROVIDER
        self._local_engine = None
        
        if self.provider == "local":
            self._init_local()
        elif self.provider == "openai":
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            
    def _init_local(self):
        try:
            self._local_engine = pyttsx3.init()
            self._local_engine.setProperty('rate', 175) # Speed
            if TTS_VOICE_ID:
                self._local_engine.setProperty('voice', TTS_VOICE_ID)
        except Exception as e:
            logger.error(f"Failed to init local TTS: {e}")

    def say(self, text: str, wait: bool = False):
        """Speak text in a background thread."""
        if not text: return
        
        if self.provider == "local" and self._local_engine:
            def _speak():
                try:
                    # pyttsx3.init() needs to be called in the same thread on some OS
                    engine = pyttsx3.init()
                    engine.setProperty('rate', 180)
                    engine.say(text)
                    engine.runAndWait()
                    engine.stop()
                except Exception as e:
                    logger.error(f"TTS error: {e}")
            
            t = threading.Thread(target=_speak, daemon=True)
            t.start()
            if wait: t.join()
            
        elif self.provider == "openai":
            def _speak_api():
                try:
                    import tempfile
                    from pygame import mixer
                    
                    response = self.client.audio.speech.create(
                        model="tts-1",
                        voice="alloy", # alloy, echo, fable, onyx, nova, shimmer
                        input=text,
                    )
                    
                    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                        response.stream_to_file(f.name)
                        tmp_path = f.name
                    
                    mixer.init()
                    mixer.music.load(tmp_path)
                    mixer.music.play()
                    while mixer.music.get_busy():
                        continue
                    mixer.quit()
                    os.unlink(tmp_path)
                except Exception as e:
                    logger.error(f"OpenAI TTS error: {e}")

            threading.Thread(target=_speak_api, daemon=True).start()

def get_tts_engine():
    return TTSEngine()
