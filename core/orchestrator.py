"""
orchestrator.py — Main JARVIS entry point.

Flow:
  Hotkey (Ctrl+Space)
    → Audio capture (VAD)
    → Whisper STT
    → Context collection
    → Intent parsing (GPT)
    → Confirm if destructive
    → Action routing + execution
    → Feedback logging
    → UI update

All I/O is non-blocking via threads. Total target latency: <4s end-to-end.
"""

import sys
import time
import signal
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv
from pynput import keyboard

# ── Adjust path for imports ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from core.audio_capture import AudioCapture
from core.stt_engine import get_stt_engine
from core.intent_parser import IntentParser
from core.context_collector import ContextCollector
from core.action_router import ActionRouter
from core.feedback_store import FeedbackStore
from executors.base_executor import BaseExecutor
from ui.overlay import Overlay, State, run_overlay_in_thread

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

# Suppress noisy sub-loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# ── Destructive intents requiring confirmation ────────────────────────────
CONFIRM_INTENTS = {"send_message", "reply_professionally"}


class JARVISOrchestrator:
    def __init__(self):
        logger.info("Initializing JARVIS...")
        self.audio = AudioCapture(vad_aggressiveness=2)
        self.stt = get_stt_engine()
        self.parser = IntentParser()
        self.context = ContextCollector()
        self.router = ActionRouter()
        self.feedback = FeedbackStore()
        self.overlay = run_overlay_in_thread()

        self._listening = False
        self._lock = threading.Lock()
        self._last_session_id: int | None = None

        logger.info("JARVIS ready. Press Ctrl+Space to start listening.")

    def _on_hotkey(self):
        """Called when Ctrl+Space is pressed."""
        with self._lock:
            if self._listening:
                logger.info("Already listening, ignoring hotkey.")
                return
            self._listening = True

        # Run pipeline in background thread (keep hotkey listener responsive)
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        t_start = time.time()
        try:
            # 1. Capture audio
            self.overlay.set_state(State.LISTENING)
            wav_bytes = self.audio.record_until_silence()
            if not wav_bytes:
                self.overlay.set_state(State.ERROR, "No speech detected")
                time.sleep(1.5)
                self.overlay.set_state(State.IDLE)
                return

            t_audio = time.time()
            logger.info(f"Audio captured in {t_audio - t_start:.2f}s")

            # 2. Speech to text
            self.overlay.set_state(State.THINKING, "Transcribing...")
            text = self.stt.transcribe(wav_bytes)
            if not text:
                self.overlay.set_state(State.ERROR, "Couldn't understand audio")
                time.sleep(1.5)
                self.overlay.set_state(State.IDLE)
                return

            t_stt = time.time()
            logger.info(f"STT done in {t_stt - t_audio:.2f}s → '{text}'")

            # 3. Collect context (parallel to intent parsing)
            ctx = self.context.collect()
            ctx.learning_hints = self.feedback.get_learning_hints()

            # 4. Parse intent
            self.overlay.set_state(State.THINKING, "Parsing intent...")
            intent = self.parser.parse(text, ctx)

            t_parse = time.time()
            logger.info(f"Intent parsed in {t_parse - t_stt:.2f}s → {intent.intent}")

            if intent.intent == "unknown":
                self._last_session_id = self.feedback.log(
                    intent, False, "Unknown intent", context=ctx, dom_before=ctx.dom
                )
                self.overlay.set_state(State.ERROR, "Couldn't understand command")
                time.sleep(1.5)
                self.overlay.set_state(State.IDLE)
                return

            # 5. Confirm destructive actions
            detail = f"{intent.intent} → {intent.app}"
            if intent.target:
                detail += f" [{intent.target}]"
            self.overlay.set_state(State.THINKING, detail)

            if intent.intent in CONFIRM_INTENTS:
                confirmed = self._get_confirmation(intent)
                if not confirmed:
                    self._last_session_id = self.feedback.log(
                        intent, False, "Cancelled by user", context=ctx, dom_before=ctx.dom
                    )
                    self.overlay.set_state(State.IDLE, "Cancelled")
                    return

            # 6. Execute action
            self.overlay.set_state(State.EXECUTING)
            dom_before = BaseExecutor.observe_active_page() or ctx.dom
            success, result_msg = self.router.route(intent, ctx)
            dom_after = BaseExecutor.observe_active_page()

            t_exec = time.time()
            total = t_exec - t_start
            logger.info(f"Execution done in {t_exec - t_parse:.2f}s. Total: {total:.2f}s")

            # 7. Log to feedback store
            self._last_session_id = self.feedback.log(
                intent,
                success,
                result_msg,
                context=ctx,
                dom_before=dom_before,
                dom_after=dom_after,
            )
            self.feedback.log_ui_action_events(
                self._last_session_id,
                BaseExecutor.consume_action_events(),
            )
            self.feedback.log_page_snapshot(self._last_session_id, dom_after or dom_before)

            # 8. Update UI
            if success:
                self.overlay.set_state(State.SUCCESS, result_msg[:60])
            else:
                self.overlay.set_state(State.ERROR, result_msg[:60])

            time.sleep(2.5)
            self.overlay.set_state(State.IDLE)

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            self.overlay.set_state(State.ERROR, str(e)[:60])
            time.sleep(2)
            self.overlay.set_state(State.IDLE)
        finally:
            with self._lock:
                self._listening = False

    def _get_confirmation(self, intent) -> bool:
        """
        Simple terminal confirmation during MVP.
        TODO: Replace with overlay confirm button in v2.
        """
        msg = intent.data.get("message", "")
        print(f"\n⚡ Confirm: {intent.intent} to '{intent.target}'")
        if msg:
            print(f"   Message: '{msg[:80]}'")
        try:
            answer = input("   Send? [Y/n]: ").strip().lower()
            return answer in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def run(self):
        """Start hotkey listener (blocking)."""
        hotkey = keyboard.HotKey(
            keyboard.HotKey.parse("<ctrl>+<space>"),
            self._on_hotkey,
        )

        def on_press(key):
            try:
                hotkey.press(key)
            except Exception:
                pass

        def on_release(key):
            try:
                hotkey.release(key)
            except Exception:
                pass

        logger.info("Hotkey listener active: Ctrl+Space")
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                pass
        self._shutdown()

    def _shutdown(self):
        logger.info("Shutting down JARVIS...")
        self.audio.cleanup()
        self.feedback.close()
        from executors.base_executor import BaseExecutor
        BaseExecutor.close()


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    orchestrator = JARVISOrchestrator()
    orchestrator.run()
