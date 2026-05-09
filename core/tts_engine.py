"""
tts_engine.py — JARVIS Voice Feedback System.
Native Windows Fallback: Uses PowerShell for speech if pyttsx3 is missing.
"""

import os
import threading
import logging
import requests
import subprocess
from dotenv import load_dotenv

# Try to import pyttsx3, but we have a solid PowerShell fallback now
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    HAS_PYTTSX3 = False

load_dotenv()
logger = logging.getLogger(__name__)

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "local").strip().lower()
TTS_VOICE_ID = os.getenv("TTS_VOICE_ID", "").strip()

class TTSEngine:
    def __init__(self):
        self.provider = TTS_PROVIDER
        self._local_engine = None
        self.api_key = os.getenv("OPENAI_API_KEY")
        
        if self.provider == "local" and HAS_PYTTSX3:
            self._init_local()
            
    def _init_local(self):
        try:
            self._local_engine = pyttsx3.init()
            self._local_engine.setProperty('rate', 175)
            if TTS_VOICE_ID:
                self._local_engine.setProperty('voice', TTS_VOICE_ID)
        except Exception as e:
            logger.error(f"Failed to init local TTS: {e}")

    def say(self, text: str, wait: bool = False):
        if not text: return
        
        if self.provider == "local":
            if HAS_PYTTSX3 and self._local_engine:
                def _speak_pyttsx3():
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty('rate', 180)
                        engine.say(text)
                        engine.runAndWait()
                    except Exception:
                        self._speak_powershell(text) # Fallback to PS
                
                t = threading.Thread(target=_speak_pyttsx3, daemon=True)
                t.start()
                if wait: t.join()
            else:
                # Direct to PowerShell
                t = threading.Thread(target=self._speak_powershell, args=(text,), daemon=True)
                t.start()
                if wait: t.join()
            
        elif self.provider == "openai":
            # (OpenAI TTS implementation remains the same as before)
            self._speak_openai(text)

    def _speak_powershell(self, text: str):
        """Native Windows Speech fallback via PowerShell."""
        try:
            # Escape single quotes for PowerShell
            safe_text = text.replace("'", "''")
            ps_command = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{safe_text}')"
            subprocess.run(["powershell", "-Command", ps_command], capture_output=True, timeout=15)
        except Exception as e:
            logger.error(f"PowerShell TTS failed: {e}")

    def _speak_openai(self, text: str):
        def _speak_api():
            try:
                import tempfile
                from pygame import mixer
                
                url = "https://api.openai.com/v1/audio/speech"
                headers = {"Authorization": f"Bearer {self.api_key}"}
                payload = {"model": "tts-1", "voice": "alloy", "input": text}
                
                resp = requests.post(url, headers=headers, json=payload, timeout=20)
                resp.raise_for_status()
                
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(resp.content)
                    tmp_path = f.name
                
                mixer.init()
                mixer.music.load(tmp_path)
                mixer.music.play()
                while mixer.music.get_busy(): continue
                mixer.quit()
                os.unlink(tmp_path)
            except Exception as e:
                logger.error(f"OpenAI TTS error: {e}")
                self._speak_powershell(text) # Final fallback

        threading.Thread(target=_speak_api, daemon=True).start()

def get_tts_engine():
    return TTSEngine()
