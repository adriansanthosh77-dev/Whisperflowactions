"""
orchestrator.py — Main JARVIS entry point.

Flow:
  Hotkey (Ctrl+Space)
    → Audio capture (VAD, 500ms silence cutoff)
    → [PARALLEL] Whisper STT + Context collection
    → Streaming Planner (LLM generates steps, step 1 executes before step 2 is parsed)
    → Per-step: confirm if destructive → route → execute → log → update HUD
    → Feedback logging

All I/O is non-blocking via threads. Target latency: <3s to first action.
"""

import sys
import time
import signal
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv
try:
    from pynput import keyboard
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

# ── Adjust path for imports ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from core.audio_capture import AudioCapture
from core.stt_engine import get_stt_engine
from core.planner import Planner
from core.context_collector import ContextCollector
from core.action_router import ActionRouter
from core.feedback_store import FeedbackStore
from core.tts_engine import get_tts_engine
from core.agent_manager import get_agent_manager
from executors.base_executor import BaseExecutor
from ui.overlay import Overlay, State, run_overlay_in_thread

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("orchestrator")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# ── Destructive intents requiring confirmation ────────────────────────────
CONFIRM_INTENTS = {"send_message", "reply_professionally"}


class JARVISOrchestrator:
    def __init__(self):
        logger.info("Initializing JARVIS...")
        self.audio    = AudioCapture(vad_aggressiveness=2)
        self.stt      = get_stt_engine()
        self.tts      = get_tts_engine()
        self.planner  = Planner()
        self.agents   = get_agent_manager()
        self.context  = ContextCollector()
        self.router   = ActionRouter()
        self.feedback = FeedbackStore()
        self.overlay  = run_overlay_in_thread()

        self._listening = False
        self._abort_flag = False
        self._lock = threading.Lock()
        self._history = [] # list of {command: str, success: bool}

        logger.info("JARVIS ready. Press Ctrl+Space to start listening. Press ESC to abort.")

    def abort_execution(self):
        """Emergency stop for current plan execution."""
        with self._lock:
            if self._listening:
                logger.warning("ABORT SIGNAL RECEIVED. Stopping current task...")
                self._abort_flag = True
                self.audio.stop()
                BaseExecutor.close_active_page_tasks() # Signal browser to stop

    # ── Hotkey ────────────────────────────────────────────────────────────

    def _on_hotkey(self):
        with self._lock:
            if self._listening:
                return
            self._listening = True
            self._abort_flag = False
        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _on_text_hotkey(self):
        """Triggers a text input prompt on the HUD."""
        with self._lock:
            if self._listening:
                return
        
        def _get_and_run():
            text = self.overlay.prompt_text()
            if text:
                self._run_pipeline_text(text)
        
        threading.Thread(target=_get_and_run, daemon=True).start()

    # ── Main pipeline ─────────────────────────────────────────────────────

    def _run_pipeline_text(self, text: str):
        """Entry point for Terminal Mode (typed text)."""
        BaseExecutor.reset_abort_signal()
        self.overlay.set_state(State.THINKING, "Collecting context...")
        ctx = self.context.collect()
        ctx.learning_hints = self.feedback.get_learning_hints()
        ctx.history = self._history[-5:]
        self._execute_text(text, ctx)

    def _run_pipeline(self):
        t_start = time.time()
        BaseExecutor.reset_abort_signal()
        try:
            # ── 1. Capture audio ─────────────────────────────────────────
            self.overlay.set_state(State.LISTENING)
            wav_bytes = self.audio.record_until_silence()
            if self._abort_flag: 
                self.overlay.set_state(State.IDLE, "Aborted")
                return
            if not wav_bytes:
                self.overlay.set_state(State.ERROR, "No speech detected")
                time.sleep(1.2)
                self.overlay.set_state(State.IDLE)
                return

            t_audio = time.time()
            logger.info(f"Audio captured in {t_audio - t_start:.2f}s")

            # ── 2. PARALLEL: STT + Context collection ────────────────────
            if self._abort_flag: return
            self.overlay.set_state(State.THINKING, "Processing...")

            ctx_container = {"ctx": None}
            def _collect():
                c = self.context.collect()
                c.learning_hints = self.feedback.get_learning_hints()
                c.history = self._history[-5:]
                ctx_container["ctx"] = c

            ctx_thread = threading.Thread(target=_collect, daemon=True)
            ctx_thread.start()

            text = self.stt.transcribe(wav_bytes)

            ctx_thread.join()
            ctx = ctx_container["ctx"]
            if self._abort_flag: return

            t_parallel = time.time()
            if not text:
                logger.info(f"STT returned no text in {t_parallel - t_audio:.2f}s")
                self.overlay.set_state(State.ERROR, "No speech detected")
                time.sleep(1.2)
                self.overlay.set_state(State.IDLE)
                return

            logger.info(f"STT + Context ready in {t_parallel - t_audio:.2f}s → '{text}'")
            self._execute_text(text, ctx)
        
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self.overlay.set_state(State.ERROR, "System Error")
            time.sleep(1.5)
            self.overlay.set_state(State.IDLE)
        finally:
            with self._lock:
                self._listening = False

    def _execute_text(self, text: str, ctx: Context):
        # ── 3. Streaming plan execution ──────────────────────────────
        self.overlay.set_state(State.THINKING, "Planning...")

        # ── INTERCEPT: Save/Load Agent Commands ──────────────────────
        lower_text = text.lower()
        if "save this agent as" in lower_text:
            agent_name = lower_text.split("save this agent as")[-1].strip()
            if agent_name:
                self.agents.save_agent(agent_name, self.planner.custom_system_prompt or "Default JARVIS Persona")
                msg = f"Agent {agent_name} saved successfully."
                self.overlay.set_state(State.SUCCESS, msg)
                self.tts.say(msg)
                time.sleep(1.5); self.overlay.set_state(State.IDLE); return

        if "switch to" in lower_text or "load" in lower_text:
            parts = lower_text.split("switch to") if "switch to" in lower_text else lower_text.split("load")
            agent_name = parts[-1].strip().replace(" agent", "")
            
            if "default" in agent_name:
                self.planner.set_persona(None)
                msg = "Switched to default JARVIS persona."
            else:
                config = self.agents.load_agent(agent_name)
                if config:
                    self.planner.set_persona(config.get("system_prompt"))
                    msg = f"Agent {agent_name} loaded. I am ready."
                else:
                    msg = f"I couldn't find an agent named {agent_name}."
            
            self.overlay.set_state(State.SUCCESS, msg)
            self.tts.say(msg)
            time.sleep(1.5); self.overlay.set_state(State.IDLE); return

        step_num = 0
        overall_success = True
        t_parallel = time.time()

        for step in self.planner.plan(text, ctx):
            if self._abort_flag: 
                self.overlay.set_state(State.IDLE, "Aborted")
                self.tts.say("Task aborted.")
                break
            step_num += 1

            if step.intent == "unknown" or step.confidence < 0.5:
                self.feedback.log(step, False, "Unknown intent", context=ctx)
                self.overlay.set_state(State.ERROR, f"Step {step_num}: couldn't understand")
                self.tts.say("I didn't quite catch that.")
                time.sleep(1.0)
                continue

            # Execute step
            self.overlay.set_state(State.EXECUTING, f"Step {step_num}: {step.intent}")
            self.tts.say(f"Executing {step.intent}")
            
            # Simple native CDP check
            success, result_msg = self.router.route(step, ctx)

            t_step = time.time()
            logger.info(f"Step {step_num} done in {t_step - t_parallel:.2f}s: {result_msg}")

            if not success:
                overall_success = False
                self.overlay.set_state(State.ERROR, f"Step {step_num} failed.")
                break
            else:
                self.overlay.set_state(State.SUCCESS, result_msg[:60])
                time.sleep(0.8)

        if overall_success:
            self.overlay.set_state(State.SUCCESS, "All tasks completed.")
            self.tts.say("All tasks completed.")
        
        time.sleep(1.5)
        self.overlay.set_state(State.IDLE)

        # ── 5. Log to session history ────────────────────────────────
        self._history.append({
            "command": text,
            "success": overall_success,
            "timestamp": time.time()
        })
        self._history = self._history[-10:] # Keep last 10 local

        self.overlay.set_state(State.IDLE)

    # ── Confirmation ──────────────────────────────────────────────────────

    def _get_confirmation(self, step) -> bool:
        """
        Simple terminal confirmation during MVP.
        TODO: Replace with overlay confirm button in v2.
        """
        msg = step.data.get("message", "")
        print(f"\n⚡ Confirm: {step.intent} to '{step.target}'")
        if msg:
            print(f"   Message: '{msg[:80]}'")
        try:
            answer = input("   Proceed? [Y/n]: ").strip().lower()
            return answer in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Hotkey listener ───────────────────────────────────────────────────

    def run(self):
        if not HAS_PYNPUT:
            logger.warning("Hotkey listener (pynput) missing. Running in Terminal Mode.")
            logger.info("Type your command below (or 'exit' to quit):")
            while True:
                try:
                    text = input("\nJARVIS > ").strip()
                    if text.lower() in ("exit", "quit"): break
                    if text:
                        # Fake a pipeline run with the typed text
                        self._run_pipeline_text(text)
                except (EOFError, KeyboardInterrupt):
                    break
            self._shutdown()
            return

        # We'll use a set to track pressed keys for the PTT (Push-To-Talk) behavior
        pressed_keys = set()
        
        # Define our activation keys
        TRIGGER_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.space}
        
        def on_press(key):
            if key == keyboard.Key.esc:
                self.abort_execution()
                return

            if key in pressed_keys:
                return
            pressed_keys.add(key)
            
            # Check for Ctrl+Shift+Space
            is_ctrl = keyboard.Key.ctrl_l in pressed_keys or keyboard.Key.ctrl_r in pressed_keys
            is_alt = keyboard.Key.alt_l in pressed_keys or keyboard.Key.alt_r in pressed_keys
            is_shift = keyboard.Key.shift in pressed_keys or keyboard.Key.shift_r in pressed_keys
            is_space = keyboard.Key.space in pressed_keys
            
            if is_ctrl and is_shift and is_space:
                self._on_text_hotkey()
            elif (is_ctrl or is_alt) and is_space:
                self._on_hotkey()

        def on_release(key):
            if key in pressed_keys:
                pressed_keys.remove(key)
            
            # If we were listening and released a trigger key, stop recording
            if self._listening:
                # If they release space OR ctrl OR alt, we consider the push-to-talk over
                if key == keyboard.Key.space or key in {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.alt_l, keyboard.Key.alt_r}:
                    logger.info("Trigger key released. Stopping recording...")
                    self.audio.stop()

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
        BaseExecutor.close()


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    orchestrator = JARVISOrchestrator()
    orchestrator.run()
