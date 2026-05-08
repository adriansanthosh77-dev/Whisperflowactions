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
from pynput import keyboard

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

    # ── Main pipeline ─────────────────────────────────────────────────────

    def _run_pipeline(self):
        t_start = time.time()
        BaseExecutor.reset_abort_signal() # Reset browser abort signal
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
                c.history = self._history[-5:] # Only send last 5 interactions
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

            # ── 3. Streaming plan execution ──────────────────────────────
            self.overlay.set_state(State.THINKING, "Planning...")

            # ── INTERCEPT: Save/Load Agent Commands ──────────────────────
            lower_text = text.lower()
            if "save this agent as" in lower_text:
                agent_name = lower_text.split("save this agent as")[-1].strip()
                if agent_name:
                    self.agents.save_agent(agent_name, self.planner.custom_system_prompt or self.planner.PLANNER_PROMPT)
                    msg = f"Agent {agent_name} saved successfully."
                    self.overlay.set_state(State.SUCCESS, msg)
                    self.tts.say(msg)
                    time.sleep(1.5); self.overlay.set_state(State.IDLE); return

            if "switch to" in lower_text or "load" in lower_text:
                # Find agent name: "switch to research expert" -> "research expert"
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

                # Confirm destructive steps
                detail = f"{step.intent} → {step.app}"
                if step.target:
                    detail += f" [{step.target}]"

                if step.intent in CONFIRM_INTENTS:
                    self.overlay.set_state(State.THINKING, f"Confirm: {detail}")
                    if not self._get_confirmation(step):
                        self.feedback.log(step, False, "Cancelled by user", context=ctx)
                        self.overlay.set_state(State.IDLE, "Cancelled")
                        return

                # ── 4. Check for Robot Checks / CAPTCHAs ────────────────
                is_blocked, reason = BaseExecutor.check_for_block()
                if is_blocked:
                    logger.warning(f"Automation blocked: {reason}")
                    self.overlay.set_state(State.ERROR, "Robot check detected! Please solve it.")
                    print(f"\n🛑 BLOCK DETECTED: {reason}")
                    print("   Please solve the CAPTCHA/Login in the browser.")
                    input("   Press [Enter] once solved to continue...")
                    self.overlay.set_state(State.THINKING, "Resuming...")
                    # Re-collect DOM after user intervention
                    dom_after = BaseExecutor.observe_active_page()

                # Execute step
                self.overlay.set_state(State.EXECUTING, f"Step {step_num}: {step.intent}")
                self.tts.say(f"Executing {step.intent}")
                dom_before = BaseExecutor.observe_active_page() or ctx.dom
                success, result_msg = self.router.route(step, ctx)
                dom_after = BaseExecutor.observe_active_page()

                t_step = time.time()
                logger.info(f"Step {step_num} done in {t_step - t_parallel:.2f}s: {result_msg}")

                # Log step to feedback store
                session_id = self.feedback.log(
                    step, success, result_msg, context=ctx,
                    dom_before=dom_before, dom_after=dom_after,
                )
                self.feedback.log_ui_action_events(
                    session_id, BaseExecutor.consume_action_events()
                )
                self.feedback.log_page_snapshot(session_id, dom_after or dom_before)

                if not success:
                    overall_success = False
                    self.overlay.set_state(State.ERROR, f"Step {step_num} failed. Re-planning...")
                    logger.warning(f"Step {step_num} failed: {result_msg}. Triggering dynamic re-plan...")
                    
                    # ── DYNAMIC RE-PLAN ─────────────────────────────────────
                    # We capture the NEW context and ask the planner to finish the original goal
                    # but starting from this error state.
                    time.sleep(1.0)
                    new_ctx = self.context.collect()
                    new_ctx.learning_hints = self.feedback.get_learning_hints()
                    
                    # We continue the outer loop with a recursive-like call to plan()
                    # but we simplify by just breaking and letting the user know or 
                    # we can actually loop back. Let's loop back for 1 retry.
                    recovery_success = False
                    for retry_step in self.planner.plan(f"Finish the goal: {text} (Note: {result_msg} just happened)", new_ctx):
                        step_num += 1
                        self.overlay.set_state(State.EXECUTING, f"Retry Step {step_num}: {retry_step.intent}")
                        s2, m2 = self.router.route(retry_step, new_ctx)
                        if s2:
                            self.overlay.set_state(State.SUCCESS, "Recovery successful")
                            time.sleep(0.8)
                            recovery_success = True
                        else:
                            # ── DIAGNOSE FAILURE ────────────────────────────
                            diagnosis = self.router.browser_executor.diagnose_failure(text, [f"{step.intent}:{result_msg}"])
                            self.overlay.set_state(State.ERROR, diagnosis[:60])
                            logger.error(f"Recovery failed. Diagnosis: {diagnosis}")
                            return # Hard stop if recovery fails
                    
                    if not recovery_success:
                        break # Exit the main step loop if recovery was never even yielded or finished
                    
                    break # Finished recovery plan successfully
                else:
                    self.overlay.set_state(State.SUCCESS, result_msg[:60])
                    time.sleep(0.8)  # brief success flash before next step

                # Update ctx DOM for next step (page may have changed)
                if dom_after:
                    ctx.dom = dom_after

            if step_num == 0:
                self.overlay.set_state(State.ERROR, "No actions found")
                time.sleep(1.5)
            elif overall_success:
                total = time.time() - t_start
                self.overlay.set_state(State.SUCCESS, f"Done ({total:.1f}s)")
                time.sleep(2.0)
            else:
                self.overlay.set_state(State.ERROR, "Some steps failed")
                time.sleep(2.0)

            # ── 5. Log to session history ────────────────────────────────
            self._history.append({
                "command": text,
                "success": overall_success,
                "timestamp": time.time()
            })
            self._history = self._history[-10:] # Keep last 10 local

            self.overlay.set_state(State.IDLE)

        except Exception as e:
            logger.exception(f"Pipeline error: {e}")
            self.overlay.set_state(State.ERROR, str(e)[:60])
            time.sleep(2)
            self.overlay.set_state(State.IDLE)
        finally:
            with self._lock:
                self._listening = False

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
        # We'll use a set to track pressed keys for the PTT (Push-To-Talk) behavior
        pressed_keys = set()
        
        # Define our activation keys
        TRIGGER_KEYS = {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.space}
        REQUIRED_COMBO = {keyboard.Key.ctrl_l, keyboard.Key.space} # Can also be ctrl_r
        
        def on_press(key):
            if key == keyboard.Key.esc:
                self.abort_execution()
                return

            if key in pressed_keys:
                return
            pressed_keys.add(key)
            
            # Check for Ctrl+Space
            is_ctrl = keyboard.Key.ctrl_l in pressed_keys or keyboard.Key.ctrl_r in pressed_keys
            # Check for Alt+Space
            is_alt = keyboard.Key.alt_l in pressed_keys or keyboard.Key.alt_r in pressed_keys
            
            is_space = keyboard.Key.space in pressed_keys
            
            if (is_ctrl or is_alt) and is_space:
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
