"""
orchestrator.py — Main JARVIS entry point.

Flow:
  Hotkey: Hold Shift (voice) or Ctrl+Shift+Space (text)
    → Audio capture (VAD, 500ms silence cutoff)
    → [PARALLEL] Whisper STT + Context collection
    → Streaming Planner (LLM generates steps, step 1 executes before step 2 is parsed)
    → Per-step: confirm if destructive → route → execute → log → update HUD
    → Feedback logging

All I/O is non-blocking via threads. Target latency: <3s to first action.
"""

import sys
import os
import time
import atexit
import signal
import logging
import threading
import queue
import collections
import concurrent.futures
from pathlib import Path
import requests as http_requests
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
from core.vision_engine import get_vision_engine
from core.action_router import ActionRouter
from core.feedback_store import FeedbackStore
from core.tts_engine import get_tts_engine
from core.agent_manager import get_agent_manager
from core.memory_store import get_memory
from core.telemetry import get_telemetry, SessionMetric
from core.overwatch import start_overwatch
from executors.base_executor import BaseExecutor
from core.setup_wizard import needs_setup, run_setup_wizard
from core.vision_assistant import get_vision_assistant
from ui.overlay import Overlay, State, run_overlay_in_thread
from ui.tray import run_tray_in_thread
from models.intent_schema import Context, IntentResult

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

# ── Wake word threshold (0.0‑1.0; lower = more sensitive, higher = fewer false triggers) ──
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))


class JARVISOrchestrator:
    def __init__(self):
        logger.info("Initializing JARVIS...")

        if needs_setup():
            logger.info("First-run detected. Launching setup wizard...")
            print("\n" + "=" * 65)
            print("  FIRST RUN DETECTED — Launching Setup Wizard")
            print("=" * 65 + "\n")
            run_setup_wizard()
            load_dotenv(override=True)

        # Intent sequencer: classifies commands into tiers (reflex, research, coding, complex...)
        from core.intent_sequencer import IntentSequencer
        self.intent_sequencer = IntentSequencer()
        logger.info("IntentSequencer loaded")

        self.audio    = AudioCapture(energy_callback=lambda e: self.overlay.set_audio_energy(e))
        self.stt      = get_stt_engine()
        self.tts      = get_tts_engine()
        self.planner  = Planner()
        self.vision   = get_vision_engine()
        self.vision_assistant = get_vision_assistant(self.vision)
        self.agents   = get_agent_manager()
        self.context  = ContextCollector()
        self.router   = ActionRouter()
        self.feedback = FeedbackStore()
        self.memory   = get_memory()
        self.telemetry = get_telemetry()
        self.overlay  = run_overlay_in_thread(wake_callback=lambda: self._on_hotkey_wake())

        self._listening = False
        self._dictation_active = False
        self._abort_flag = False
        self._lock = threading.Lock()
        self._history = []
        self._first_wake_done = False
        self._pipeline_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=os.cpu_count() or 4,
            thread_name_prefix="jarvis_pipeline",
        )

        # The browser will launch automatically on the first web-related command.
        logger.info("Browser Status: On-Demand (Will launch when needed)")
        
        logger.info("--- Available Reflexes ---")
        reflexes = self.planner.list_reflexes()
        for r in reflexes:
            logger.info(f"  > {r}")
        logger.info("--------------------------")
        
        # Broadcast supported reflexes to the HUD after a short delay
        threading.Timer(3.0, lambda: self.overlay.show_reflexes(reflexes)).start()

        # Cinematic Startup Sequence
        def _startup_routine():
            logger.info("Starting cinematic boot sequence...")
            # Wait for HUD WebSocket to connect
            time.sleep(2.0)
            
            import datetime
            now = datetime.datetime.now()
            hour = now.hour
            title = os.getenv("USER_TITLE", "sir")
            
            # Step 1: Quick greeting
            logger.info("Cinematic: Greeting...")
            greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
            
            self.overlay.set_state(State.SUCCESS, "ALL SYSTEMS NOMINAL", fullscreen=True)
            self.tts.say(f"{greeting} {title}. JARVIS is online.")
            self._first_wake_done = True
            self.overlay.startup_complete = True
            
            # Shrink to corner
            logger.info("Cinematic: Minimizing HUD...")
            time.sleep(0.3)
            self.overlay.set_state(State.IDLE, "SYSTEM READY", fullscreen=False)

        threading.Thread(target=_startup_routine, daemon=True).start()

        logger.info("JARVIS ready. Hold Shift to talk. Ctrl+Shift+Space for text. ESC to abort.")
        self._start_sleep_timer()
        
        start_overwatch(self._on_proactive_trigger)

        # Start system tray icon
        self._tray = run_tray_in_thread(
            on_show=lambda: self.overlay.set_state(self.overlay.current_state, self.overlay.detail, fullscreen=True),
            on_quit=self.stop,
            on_toggle_listen=self._toggle_listening,
        )

        # Start reminder checker
        self._start_reminder_checker()

        # Register block handler for browser automation
        BaseExecutor.set_block_handler(self._default_block_handler)
        BaseExecutor.start_keepalive()

        # Load plugins
        from core.plugin_manager import get_plugin_manager
        self._plugin_manager = get_plugin_manager()
        self._plugin_manager.load_all()

        # Ensure HUD is killed on abrupt exit (belt-and-suspenders with Job Object)
        atexit.register(self._kill_hud)

    def _kill_hud(self):
        """Force-kill the HUD Electron process on abrupt exit."""
        if hasattr(self, 'overlay'):
            self.overlay.stop()

    def stop(self):
        """Shutdown all JARVIS components."""
        logger.info("Shutting down JARVIS...")
        self._abort_flag = True
        if hasattr(self, '_tray'):
            self._tray.stop()
        if hasattr(self, 'overlay'):
            self.overlay.stop()
    def _toggle_listening(self):
        self._listening = not self._listening
        state = State.LISTENING if self._listening else State.IDLE
        detail = "Listening..." if self._listening else "Idle"
        self.overlay.set_state(state, detail)

    def _default_block_handler(self, reason: str) -> bool:
        logger.info(f"Block detected: {reason}")
        tag = reason.split(":")[0] if ":" in reason else "block"

        self.overlay.set_state(State.ERROR, f"Blocked: {tag}")

        messages = {
            "captcha": "I've hit a captcha or robot check. Please complete it, then let me know.",
            "login_wall": "I've hit a login screen. Please sign in, then let me know.",
            "payment": "I've found a payment or credit card form. Please fill in the sensitive details, then let me know.",
            "generic_block": "I've been blocked. Please handle it, then let me know.",
        }
        msg = messages.get(tag, f"I've encountered a {tag} screen. Please handle it, then let me know.")
        self.tts.say(msg, wait=True)

        screenshot_path = BaseExecutor.capture_full_screenshot("data/block_screenshot.png")
        if screenshot_path:
            self.overlay.set_state(State.ERROR, f"Blocked: {tag} — Please handle it")

        handled = self.overlay.prompt_blocked(
            title=f"JARVIS Blocked — {tag}",
            description=f"{msg}\n\nHandle it in the browser, then click 'Continue'.",
        )

        if handled:
            self.tts.say("Thank you. Resuming.", wait=False)
            self.overlay.set_state(State.IDLE, "Resuming...")
            time.sleep(1.0)
            return True

        self.tts.say("Aborting this task.", wait=False)
        self.overlay.set_state(State.IDLE, "Aborted")
        return False

    def _on_proactive_trigger(self, title: str, suggestion: str):
        """Callback for background window events."""
        logger.info(f"Proactive Suggestion: {suggestion} for {title}")
        # Only suggest if not busy
        if not self._listening:
            msg = f"I noticed you're on {suggestion}. Would you like some help?"
            self.overlay.set_state(State.IDLE, f"💡 {suggestion}")
            self.tts.say(msg)

    def _start_reminder_checker(self):
        def _check():
            while not self._abort_flag:
                try:
                    reminders = []
                    try:
                        reminders = self.feedback.get_due_reminders()
                    except AttributeError:
                        pass
                    for r in reminders:
                        msg = f"Reminder: {r['text']}"
                        logger.info(msg)
                        self.tts.say(msg)
                        self.overlay.set_state(State.SUCCESS, msg)
                except Exception:
                    pass
                time.sleep(5)
        threading.Thread(target=_check, daemon=True).start()

    def _on_hotkey_wake(self):
        """Internal trigger for wake word routine."""
        with self._lock:
            if self._listening: return
            self._listening = True
        
        def _run():
            ctx = self.context.collect(light=True)
            self._handle_wake_routine(ctx)
            self._listening = False

        threading.Thread(target=_run, daemon=True).start()

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
            self._last_activity = time.time() # Reset sleep timer on manual trigger
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
        self._last_activity = time.time() # Reset sleep timer
        self._abort_flag = False
        self.overlay.set_state(State.THINKING, "Collecting context...")
        ctx = self.context.collect(light=True)
        ctx.learning_hints = self.feedback.get_learning_hints()
        ctx.history = self._history[-5:]
        self._execute_text(text, ctx)

    def _toggle_dictation(self):
        """Toggle dictation mode on/off from hotkey."""
        with self._lock:
            if self._dictation_active:
                self._dictation_active = False
                self._listening = False
                self.overlay.set_state(State.SUCCESS, "Dictation ended")
                self.tts.say("Dictation ended.")
                return
            if self._listening:
                return
            self._dictation_active = True
            self._listening = True
            self._abort_flag = False
        threading.Thread(target=self._dictation_mode, daemon=True).start()

    def _dictation_mode(self):
        """Continuous dictation loop: speak → transcribe → type into active app."""
        self._last_activity = time.time()
        self.overlay.set_state(State.LISTENING, "Dictation mode — speak")
        self.tts.say("Dictation mode activated.")
        ctx = self.context.collect(light=True)

        while self._dictation_active and not self._abort_flag:
            wav_bytes = self.audio.record_until_silence(push_to_talk=False)
            if self._abort_flag or not self._dictation_active:
                break
            if not wav_bytes:
                self.overlay.set_state(State.LISTENING, "Dictation mode — speak")
                continue

            result = self.stt.transcribe(wav_bytes, on_segment=lambda seg: self.overlay.set_state(State.LISTENING, f"Hearing: {seg[:60]}"))
            if not result:
                self.overlay.set_state(State.LISTENING, "Dictation mode — speak")
                continue

            text = result.text
            if not text:
                continue

            lower = text.lower().strip()
            if lower in ("stop dictation", "end dictation", "exit dictation"):
                self._dictation_active = False
                self.tts.say("Dictation ended.")
                break

            self.overlay.set_state(State.EXECUTING, f"Typing: {text[:50]}")
            step = IntentResult(
                intent="pc_action",
                app="pc",
                target=text,
                data={"operation": "type", "text": text},
                confidence=result.confidence,
                raw_text=text,
            )
            success, msg = self.router.route(step, ctx)
            if success:
                self.overlay.set_state(State.SUCCESS, f"Typed: {text[:40]}")
            else:
                self.overlay.set_state(State.ERROR, f"Type failed: {msg[:30]}")
            time.sleep(0.3)
            self._last_activity = time.time()

        with self._lock:
            self._dictation_active = False
            self._listening = False
        self.overlay.set_state(State.IDLE)

    def _run_pipeline(self):
        t_start = time.time()
        self._abort_flag = False
        self.overlay.set_state(State.THINKING, "Collecting context...", fullscreen=False)
        try:
            # ── 1. Capture audio with predictive context ───────────────────
            self.overlay.set_state(State.LISTENING)
            
            # START PREDICATIVE CONTEXT COLLECTION in background while user talks
            # This captures the DOM and URL while the user is still speaking.
            ctx_future = self._pipeline_pool.submit(self.context.collect, light=True)

            wav_bytes = self.audio.record_until_silence(push_to_talk=True)
            if self._abort_flag: 
                self.overlay.set_state(State.IDLE, "Aborted")
                return
            if not wav_bytes:
                self.overlay.set_state(State.ERROR, "No speech detected")
                time.sleep(0.5)
                self.overlay.set_state(State.IDLE)
                return

            t_audio = time.time()
            logger.info(f"Audio captured in {t_audio - t_start:.2f}s")

            # ── 2. FIRE STT IMMEDIATELY (doesn't depend on context) ──
            if self._abort_flag: return
            self.overlay.set_state(State.THINKING, "Processing...")

            stt_future = self._pipeline_pool.submit(self.stt.transcribe, wav_bytes)

            # Wait for STT (context collection finishes independently)
            stt_result = stt_future.result(timeout=300)
            if self._abort_flag: return

            t_parallel = time.time()
            if not stt_result:
                logger.info(f"STT returned no text in {t_parallel - t_audio:.2f}s")
                self.overlay.set_state(State.ERROR, "No speech detected")
                self.tts.say("I didn't catch that. Could you repeat it?")
                time.sleep(0.3)
                wav_bytes = self.audio.record_until_silence(push_to_talk=True)
                if wav_bytes:
                    stt_result = self.stt.transcribe(wav_bytes)
                if not stt_result:
                    self.overlay.set_state(State.IDLE)
                    return

            # Get context (it's been collecting in parallel this whole time)
            ctx = ctx_future.result(timeout=300)
            t_context = time.time()

            text = stt_result.text
            logger.info(f"STT ready in {t_parallel - t_audio:.2f}s → '{text}'")

            logger.info("Context ready in %.2fs (waited %.2fs after STT)", t_context - t_start, t_context - t_parallel)
            lower_text = text.lower().strip()
            if lower_text in ("start dictation", "begin dictation", "dictation mode"):
                self._dictation_mode()
                return
            if lower_text in ("stop dictation", "end dictation", "exit dictation"):
                self.overlay.set_state(State.SUCCESS, "Dictation ended")
                self.tts.say("Dictation ended.")
                self._listening = False
                return

            if stt_result.low_confidence:
                low_words = ", ".join(w["word"] for w in stt_result.low_conf_words[:5])
                logger.warning(f"Low confidence words: {low_words}")
                self.overlay.set_state(State.LISTENING, f"Did you mean: {text}?")
                time.sleep(0.5)
            
            t_plan_start = time.time()
            try:
                success = self._execute_text(text, ctx)
                t_end = time.time()
                logger.info(
                    "Pipeline timing: capture=%.2fs stt=%.2fs context_wait=%.2fs execute=%.2fs total=%.2fs",
                    t_audio - t_start,
                    t_parallel - t_audio,
                    t_context - t_parallel,
                    t_end - t_plan_start,
                    t_end - t_start,
                )
                
                metric = SessionMetric(
                    timestamp=t_start, command=text,
                    stt_latency=t_parallel - t_audio,
                    planning_latency=t_end - t_plan_start,
                    execution_latency=0.0, total_latency=t_end - t_start,
                    success=success,
                )
                self.telemetry.log_session(metric)
            except KeyboardInterrupt:
                logger.warning("User interrupted execution (Ctrl-C). Aborting task.")
                self.abort_execution()
                self.overlay.set_state(State.IDLE, "Aborted")
                self.tts.say("Task aborted.")
        
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self.overlay.set_state(State.ERROR, "System Error")
            time.sleep(1.5)
            self.overlay.set_state(State.IDLE)
        finally:
            with self._lock:
                self._listening = False

    def _execute_text(self, text: str, ctx: Context):
        # ── SPLIT COMPOUND COMMANDS (e.g. "volume up then mute") ──
        import re
        parts = re.split(r"\s+(?:and\s+)?then\s+|\s*,\s*then\s+|\s+and\s+then\s+|\s*;\s*", text.strip(), flags=re.I)
        if len(parts) > 1:
            logger.info(f"Compound command: {len(parts)} parts")
            overall = True
            for i, part in enumerate(parts):
                p = part.strip()
                if not p:
                    continue
                if i > 0:
                    self.tts.say(f"Next: {p[:60]}", wait=True)
                if self._abort_flag:
                    break
                ok = self._execute_single(p, ctx)
                if not ok:
                    overall = False
                    break
            return overall

        return self._execute_single(text, ctx)

    def _execute_single(self, text: str, ctx: Context):
        # ── 3. Streaming plan execution ──────────────────────────────
        self.overlay.set_state(State.THINKING, "Planning...")

        # --- INTERCEPT: Check for Reflex or Taught Workflow first ---
        lower_text = text.lower()
        taught = None
        try:
            taught = self.feedback.get_taught_workflow(text)
        except AttributeError:
            pass
        is_reflex = self.planner.can_fast_plan(text)
        from core.brain_router import detect_task_type
        task_type = detect_task_type(text)
        
        # If it's not a known reflex, route plain text through the "type" operation.
        # This way typing "hello world" in chat mode types it into the active app.
        if not taught and not is_reflex and task_type == "general" and not any(k in lower_text for k in ["teach me", "teach jarvis", "save this agent", "switch to", "load", "?"]):
            from executors.pc_executor import PCExecutor
            from core.planner import IntentResult
            intent = IntentResult(intent="pc_action", target=text,
                                  data={"operation": "type", "text": text, "safety_level": "safe"},
                                  confidence=0.9, raw_text=text)
            success, msg = PCExecutor().execute(intent, ctx)
            if success:
                self.overlay.set_state(State.SUCCESS, f"Typed: {text[:40]}")
            else:
                self.overlay.set_state(State.ERROR, f"Type failed: {msg[:30]}")
            return

        step_num = 0
        overall_success = True
        for step in self.planner.plan(text, ctx):
            if self._abort_flag: 
                self.overlay.set_state(State.IDLE, "Aborted")
                self.tts.say("Task aborted.")
                break
            step_num += 1

            if step.intent == "dictation_mode":
                if step.data.get("operation") == "start":
                    self._dictation_mode()
                return

            if step.intent == "unknown" or step.confidence < 0.5:
                self.feedback.log(step, False, "Unknown intent", context=ctx)
                if step_num == 1:
                    self._offer_teach_options(text)
                    return
                
                self.overlay.set_state(State.ERROR, f"Step {step_num}: couldn't understand")
                self.tts.say("I didn't quite catch that.")
                time.sleep(0.4)
                continue


            # --- ⏰ INTERCEPT: Reminders ---
            if step.intent == "reminder":
                text = step.data.get("text", "")
                delay = step.data.get("delay_seconds", 60)
                try:
                    self.feedback.set_reminder(text, delay)
                except AttributeError:
                    pass
                display = f"{delay//60}m" if delay < 3600 else f"{delay//3600}h"
                self.overlay.set_state(State.SUCCESS, f"Reminder set for {display}")
                self.tts.say(f"I'll remind you in {display}.")
                self.feedback.log(step, True, f"Reminder set for {display}s", context=ctx)
                overall_success = True
                continue

            # --- 🛑 INTERCEPT: Decision Prompts (Brain Routing / Visibility) ---
            if step.data.get("mode") == "decision_prompt":
                self._handle_decision_flow(step, text, ctx)
                return

            needs_confirm = (
                step.data.get("requires_confirmation")
                or step.data.get("safety_level") == "confirm"
                or (step.intent in CONFIRM_INTENTS and not step.data.get("draft_only"))
            )
            if needs_confirm:
                if not self._get_confirmation(step):
                    overall_success = False
                    self.overlay.set_state(State.IDLE, "Cancelled")
                    self.tts.say("Cancelled.")
                    break

            # Execute step
            self.overlay.set_state(State.EXECUTING, f"Step {step_num}: {step.intent}")
            
            # --- 📸 SPECIAL HANDLING: Vision / Describe Screen ---
            if step.intent == "describe_screen":
                self.tts.say("Let me take a look.")
                screenshot_path = BaseExecutor.capture_full_screenshot()
                query = step.data.get("query", "Describe what is on the screen.")
                description = self.vision.analyze_screenshot(screenshot_path, query)
                
                def _on_spk(): self.overlay.set_state(State.SPEAKING, "I've analyzed the screen.")
                def _on_end(): 
                    if self.overlay.current_state == State.SPEAKING:
                        self.overlay.set_state(State.SUCCESS, "Analysis complete.")
                self.tts.say(description, on_start=_on_spk, on_end=_on_end)
                success, result_msg = True, description
            # --- 🌞 SPECIAL: Wake Word / Morning Routine ---
            if step.intent == "chat" and step.data.get("topic") == "wake_routine":
                self._handle_wake_routine(ctx)
                return

            else:
                def _on_spk(): self.overlay.set_state(State.SPEAKING, f"Executing {step.intent}")
                def _on_end(): 
                    if self.overlay.current_state == State.SPEAKING:
                        self.overlay.set_state(State.EXECUTING, f"Running {step.intent}...")
                self.tts.say(f"Executing {step.intent}", on_start=_on_spk, on_end=_on_end)
                # Simple native CDP check
                dom_before = {}
                if step.intent in ("browser_action", "open_app", "summarize", "send_message", "create_task"):
                    try:
                        dom_before = BaseExecutor.observe_active_page()
                    except Exception:
                        dom_before = {}
                success, result_msg = self.router.route(step, ctx)
            blocked, reason = BaseExecutor.check_for_block()
            if blocked:
                allowed = self._request_permission(reason)
                if not allowed:
                    overall_success = False
                    def _on_spk(): self.overlay.set_state(State.SPEAKING, "Permission denied")
                    def _on_end(): 
                        if self.overlay.current_state == State.SPEAKING:
                            self.overlay.set_state(State.ERROR, "Permission denied")
                    self.tts.say("Permission denied. I stopped the task.", on_start=_on_spk, on_end=_on_end)
                    break
                result_msg = f"Permission handled: {reason}"

            t_step = time.time()
            logger.info(f"Step {step_num} done: {result_msg}")
            dom_after = {}
            if step.intent in ("browser_action", "open_app", "summarize", "send_message", "create_task"):
                try:
                    dom_after = BaseExecutor.observe_active_page()
                except Exception:
                    dom_after = {}
            session_id = self.feedback.log(
                step,
                success and not blocked,
                result_msg,
                context=ctx,
                dom_before=dom_before,
                dom_after=dom_after,
            )
            self.feedback.log_ui_action_events(session_id, BaseExecutor.consume_action_events())
            self.feedback.log_page_snapshot(session_id, dom_after)

            if not success:
                overall_success = False
                self.overlay.set_state(State.ERROR, f"Step {step_num} failed.")
                self._offer_teach_mode(text, result_msg)
                break
            elif "Locked the PC" in result_msg:
                break  # PC locked — skip HUD/TTS
            else:
                self.overlay.set_state(State.SUCCESS, result_msg[:60])
                time.sleep(0.15)

        if "Locked the PC" in result_msg:
            return True

        if overall_success:
            self.overlay.set_state(State.SUCCESS, "Done.")
            self.tts.say("All tasks completed.")

        time.sleep(0.5)
        self.overlay.set_state(State.IDLE)

        # ── 5. Log to session history ────────────────────────────────
        self._record_history(text, overall_success)

        self.overlay.set_state(State.IDLE)
        self._last_activity = time.time()
        return overall_success

    def _handle_wake_routine(self, ctx: Context):
        """Perform the premium morning briefing routine or a simple wake up."""
        import datetime
        now = datetime.datetime.now()
        hour = now.hour
        title = os.getenv("USER_TITLE", "sir")
        
        # 1. Full Screen Neural Core
        self.overlay.set_state(State.THINKING, "Waking up...", fullscreen=True)

        if not self._first_wake_done:
            # --- 🌞 FULL MORNING BRIEFING (Only once) ---
            greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
            self.tts.say(f"{greeting} {title}. I am online and ready.")
            
            time_str = now.strftime("%I:%M %p")
            weather = os.getenv("WEATHER_DESCRIPTION", "")
            if not weather:
                try:
                    resp = http_requests.get("https://wttr.in/?format=%t+%C", timeout=5)
                    if resp.status_code == 200:
                        weather = resp.text.strip()
                except Exception:
                    pass
                if not weather:
                    weather = "currently 22 degrees and sunny"
            briefing = f"The time is {time_str}. The weather is {weather}."
            
            self.overlay.set_state(State.SUCCESS, f"{time_str} | {weather}", fullscreen=True)
            self.tts.say(briefing)
            self.tts.say(f"What is on your list today {title}?")
            self._first_wake_done = True
        else:
            # --- ☕ SUBSEQUENT WAKE UP (Concise) ---
            self.tts.say(f"I am here. What is on your mind today, {title}?")
        
        self.overlay.set_state(State.LISTENING, "What's on your mind?", fullscreen=True)
        self._last_activity = time.time()

    def _start_sleep_timer(self):
        """Background thread that puts JARVIS to sleep after 60s of inactivity."""
        self._last_activity = time.time()
        
        timeout = int(os.getenv("SLEEP_TIMEOUT_SECONDS", "60"))
        def _checker():
            logger.info(f"Sleep timer thread started ({timeout}s threshold).")
            while not self._abort_flag:
                time.sleep(5)
                idle_time = time.time() - self._last_activity
                
                # Check if we should sleep
                if idle_time > timeout:
                    current_detail = str(self.overlay.detail or "")
                    if "Zzz" not in current_detail:
                        logger.info(f"Inactivity detected ({idle_time:.1f}s). JARVIS going to sleep.")
                        self.overlay.set_state(State.IDLE, "Zzz...")
                
        threading.Thread(target=_checker, daemon=True).start()

    def _handle_decision_flow(self, step: IntentResult, original_text: str, ctx: Context):
        """Handles multi-stage prompts for brain choice and browser visibility."""
        task_type = step.data.get("task_type")
        prompt_text = step.data.get("text", "Choose an option:")
        
        self.overlay.set_state(State.LISTENING, prompt_text)
        self.tts.say(prompt_text, wait=True)
        
        # 1. Get user choice (Visual HUD or Voice)
        choice = self.overlay.prompt_text(title=prompt_text)
        if not choice:
            choice = self._listen_short_answer()
        
        choice = (choice or "").lower()
        if not choice:
            self.overlay.set_state(State.IDLE, "Cancelled")
            self.tts.say("Cancelled.")
            return

        # 2. Process Visibility Choice
        if task_type == "browser_visibility":
            is_stealth = any(k in choice for k in ["stealth", "background", "hide", "no"])
            BaseExecutor.toggle_stealth_mode(is_stealth)
            # Re-run the command without the flag
            self._execute_text(step.data.get("original_cmd"), ctx)
            return

        # 3. Process Brain Choice
        if "browser" in choice or "automation" in choice:
            # Trigger visibility prompt next
            self._execute_text(original_text + " BROWSER_SELECTED", ctx)
        elif "api" in choice or "premium" in choice or "fast" in choice:
            # For now, we just pass through, but could set a context flag
            self._execute_text(original_text, ctx)
        elif "local" in choice or "offline" in choice:
            self._execute_text(original_text, ctx)
        else:
            self.tts.say(f"Executing task using default {task_type} brain.")
            self._execute_text(original_text, ctx)

    def _record_history(self, text: str, success: bool):
        self._history.append({
            "command": text,
            "success": success,
            "timestamp": time.time()
        })
        self._history = self._history[-50:] # Keep last 50 for context

    def _offer_teach_mode(self, source_command: str, result_msg: str):
        if not self._should_offer_teach(result_msg):
            return
        # Use the same unified flow as the 'not found' case
        self._offer_teach_options(source_command)

    def _should_offer_teach(self, result_msg: str) -> bool:
        text = (result_msg or "").lower()
        blocked_words = [
            "refused", "forbidden", "permission denied", "blocked",
            "captcha", "login", "password", "payment", "checkout",
            "card", "credential", "unsafe",
        ]
        return not any(word in text for word in blocked_words)

    def _offer_teach_options(self, text: str):
        """Proactive Teach Mode prompt when no reflex is found. Gated by cooldown."""
        now = time.time()
        cooldown = getattr(self, "_last_teach_prompt", 0)
        if now - cooldown < 30:
            logger.info(f"Teach prompt suppressed (cooldown active) for: {text}")
            return
        self._last_teach_prompt = now
        
        logger.info(f"No reflex for: {text}")
        self.overlay.set_state(State.ERROR, "No reflex found")
        self.tts.say(
            f"I don't have a reflex for '{text}' yet. "
            "Manual or Auto? Say your choice or type it in the box.",
            wait=False
        )
        
        # Automatically show the text prompt box
        answer = self.overlay.prompt_text(title=f"Teach Mode: '{text}' (Manual or Auto?)")
        
        # If the user closed the box without typing, fallback to voice
        if not answer:
            answer = self._listen_short_answer()
            
        answer = (answer or "").lower()
        if "manual" in answer:
            self._teach_flow(text, mode="manual")
        elif "auto" in answer:
            # For auto, we might want to ask for a clearer command or just use the current one
            self.tts.say("Should I use the command as is, or would you like to say it differently? Say the command now or 'as is'.", wait=True)
            new_text = self._listen_short_answer()
            if not new_text or "as is" in new_text.lower():
                new_text = text
            self._teach_flow(new_text, mode="auto")
        else:
            self.overlay.set_state(State.IDLE, "Cancelled")
            self.tts.say("Okay, I'll ignore that for now.")

    def _teach_flow(self, text: str, mode: str = "manual"):
        """Unified teaching workflow with naming, replay, and approval."""
        self.overlay.set_state(State.TEACHING, f"Teaching ({mode})")
        
        # 1. Capture actions
        if mode == "manual":
            steps = self._capture_manual_steps(text)
        else:
            steps = self._capture_auto_steps(text)
            
        if not steps:
            self.overlay.set_state(State.ERROR, "No steps captured")
            self.tts.say("I didn't capture any replayable steps. Let's try again.")
            return

        # 2. Name the trigger
        self.tts.say(
            "What command should we use for this next time? "
            "For example: 'check my balance', 'book a flight', or 'summarize this report'.",
            wait=True
        )
        trigger = self._listen_short_answer()
        if not trigger:
             # Fallback to HUD text prompt if voice fails
             trigger = self.overlay.prompt_text() or text
        
        # 3. Verification Replay
        self.tts.say(f"Got it. I've learned the steps for '{trigger}'. Let me show you what I learned.", wait=True)
        self.overlay.set_state(State.EXECUTING, "Replaying...")
        
        # We use the router to replay, but we don't save yet
        replay_step = IntentResult(
            intent="taught_workflow",
            app="browser",
            target=trigger,
            data={"steps": steps},
            confidence=1.0,
            raw_text=text
        )
        success, msg = self.router.route(replay_step, self.context.collect(light=True))
        
        # 4. Final Approval
        if success:
            self.overlay.set_state(State.SUCCESS, "Replay success")
            self.tts.say("Did I do that correctly? Say yes to save this action, or no to try again.", wait=True)
            if self._ask_yes_no("Approve?"):
                notes = f"Learned via {mode} mode from: {text}"
                try:
                    self.feedback.save_taught_workflow(trigger, text, steps, notes=notes)
                except AttributeError:
                    pass
                self.tts.say(f"Excellent! I've saved '{trigger}' as a new action trigger.")
                self.overlay.set_state(State.SUCCESS, "Action Saved")
                time.sleep(1.5)
            else:
                self.tts.say("No problem. Let's try teaching again.")
                self._offer_teach_options(text)
        else:
            self.overlay.set_state(State.ERROR, "Replay failed")
            self.tts.say(f"I hit a snag during the replay: {msg}. Should we try manual teaching instead?")
            if self._ask_yes_no("Try manual?"):
                self._teach_flow(text, mode="manual")

    def _capture_manual_steps(self, source_command: str) -> list[dict]:
        """User shows JARVIS how to do the task."""
        self.tts.say(
            "Teach mode started. Do the task manually in the browser now. "
            "When you are finished, press Enter in this window.",
            wait=True,
        )
        stop_event = threading.Event()
        try:
            BaseExecutor.start_teach_capture()
        except Exception as e:
            logger.error(f"Manual capture start failed: {e}")
            return []

        def _poll():
            while not stop_event.is_set():
                try:
                    BaseExecutor.poll_teach_capture()
                    # Broadcast latest captured step to HUD
                    events = getattr(BaseExecutor, '_teach_events', [])
                    if events:
                        last = events[-1]
                        action = last.get("type", "?")
                        target = last.get("label") or last.get("url") or last.get("key") or last.get("selector", "")
                        self.overlay.send_teach_step(len(events), 0, action, target)
                except Exception as e:
                    logger.debug("Teach capture poll failed: %s", e)
                time.sleep(0.5)

        poller = threading.Thread(target=_poll, daemon=True)
        poller.start()
        try:
            input("\n[TEACH MODE]: Complete task in browser, then press ENTER here...")
        except (EOFError, KeyboardInterrupt):
            pass
        finally:
            stop_event.set()
            poller.join(timeout=1.0)

        steps = BaseExecutor.stop_teach_capture()
        return [s for s in steps if s.get("type") in ("navigate", "click", "fill", "press")]

    def _capture_auto_steps(self, source_command: str) -> list[dict]:
        """JARVIS uses LLM to solve the task while watching itself."""
        self.tts.say("I'll try to solve this automatically using the language model while I watch and learn.")
        try:
            BaseExecutor.start_teach_capture()
            step = IntentResult(
                intent="browser_action",
                app="browser",
                target="",
                data={"goal": source_command, "action": "auto", "max_steps": 10},
                confidence=1.0,
                raw_text=source_command
            )
            ctx = self.context.collect(light=True)
            success, _ = self.router.route(step, ctx)
            steps = BaseExecutor.stop_teach_capture()
            return [s for s in steps if s.get("type") in ("navigate", "click", "fill", "press")]
        except Exception as e:
            logger.error(f"Auto-capture failed: {e}")
            BaseExecutor.stop_teach_capture()
            return []
    def _listen_short_answer(self) -> str:
        self.overlay.set_state(State.LISTENING, "Listening")
        try:
            wav_bytes = self.audio.record_until_silence()
            result = self.stt.transcribe(wav_bytes) if wav_bytes else None
            res = result.text.strip() if result else ""
            if not res:
                # If voice fails, let the user type in the console
                logger.info("Voice capture empty, falling back to terminal input.")
                print("\n[JARVIS] I didn't catch that. Please type your answer below:")
                try:
                    res = input("Selection > ").strip()
                except (EOFError, KeyboardInterrupt):
                    res = ""
            return res
        except Exception as e:
            logger.debug("Short answer capture failed: %s", e)
            return ""

    def _ask_yes_no(self, prompt: str) -> bool:
        answer = self._listen_short_answer().lower()
        if any(word in answer for word in ["yes", "yeah", "teach", "okay", "ok"]):
            return True
        if any(word in answer for word in ["no", "stop", "cancel"]):
            return False
        try:
            answer = input(prompt).strip().lower()
            return answer in ("y", "yes", "teach", "ok", "okay")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── Confirmation ──────────────────────────────────────────────────────

    def _request_permission(self, reason: str) -> bool:
        """
        Pause on login, CAPTCHA, cookie, age, or permission walls.
        The user can manually approve or handle the page, then continue.
        """
        logger.warning("Permission wall detected: %s", reason)
        self.overlay.set_state(State.ERROR, f"Needs permission: {reason[:35]}")
        self.tts.say("I hit a permission or verification wall. Please handle it, then say yes to continue.", wait=True)
        self.overlay.set_state(State.LISTENING, "Say yes to continue, no to stop")
        try:
            wav_bytes = self.audio.record_until_silence()
            result = self.stt.transcribe(wav_bytes) if wav_bytes else None
            answer = result.text.lower().strip() if result else ""
            if answer:
                logger.info("Permission response: %s", answer)
                if any(word in answer for word in ["yes", "continue", "done", "okay", "ok"]):
                    return True
                if any(word in answer for word in ["no", "stop", "cancel"]):
                    return False
        except Exception as e:
            logger.debug("Voice permission prompt failed: %s", e)

        self.tts.say("I could not hear a clear answer. You can type yes to continue or no to stop.")
        try:
            answer = input(f"\nJARVIS needs permission: {reason}\nHandle or approve it in the browser, then continue? [y/N]: ").strip().lower()
            return answer in ("y", "yes", "continue", "done")
        except (EOFError, KeyboardInterrupt):
            return False

    def _get_confirmation(self, step) -> bool:
        msg = step.data.get("message", "")
        spoken = f"Confirm {step.intent} to {step.target}."
        if msg:
            spoken += f" Message: {msg[:120]}."
        spoken += " Say yes to continue, or no to cancel."
        self.overlay.set_state(State.LISTENING, "Confirm: say yes or no")
        self.tts.say(spoken, wait=True)
        try:
            wav_bytes = self.audio.record_until_silence()
            result = self.stt.transcribe(wav_bytes) if wav_bytes else None
            answer = result.text.lower().strip() if result else ""
            if answer:
                if any(word in answer for word in ["yes", "send", "continue", "okay", "ok"]):
                    return True
                if any(word in answer for word in ["no", "cancel", "stop"]):
                    return False
        except Exception as e:
            logger.debug("Voice confirmation failed: %s", e)

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

        def on_press(key):
            if key == keyboard.Key.esc:
                self._dictation_active = False
                self.abort_execution()
                return

            if key in pressed_keys:
                return
            pressed_keys.add(key)

            is_ctrl = keyboard.Key.ctrl_l in pressed_keys or keyboard.Key.ctrl_r in pressed_keys
            is_shift = keyboard.Key.shift in pressed_keys or keyboard.Key.shift_r in pressed_keys
            is_pause = keyboard.Key.pause in pressed_keys or key == keyboard.Key.pause
            # Also check KeyCode-based Pause (some keyboards send VK_PAUSE=0x13 as plain KeyCode)
            if not is_pause and hasattr(key, 'vk') and key.vk == 19:
                is_pause = True
            is_space = hasattr(key, 'char') and key.char == ' '

            # Ctrl+Shift+D = toggle dictation
            if is_ctrl and is_shift and hasattr(key, 'char') and key.char and key.char.lower() == 'd':
                self._toggle_dictation()
                return
            # Ctrl+Shift+Space = text mode
            if is_ctrl and is_shift and is_space:
                self._on_text_hotkey()
                return
            # Pause/Break OR Shift = voice mode
            if (is_pause or is_shift) and not is_ctrl and not self._listening:
                self._on_hotkey()

        def on_release(key):
            if key in pressed_keys:
                pressed_keys.remove(key)
            if self._listening:
                is_pause_release = key in {keyboard.Key.shift, keyboard.Key.shift_r, keyboard.Key.pause}
                if not is_pause_release and hasattr(key, 'vk') and key.vk == 19:
                    is_pause_release = True
                if is_pause_release:
                    logger.info(f"PTT released ({key}). Stopping recording...")
                    self.audio.stop()

        logger.info("Hotkeys: Hold Pause/Break (or Shift) = voice | Ctrl+Shift+Space = text")
        with keyboard.Listener(on_press=on_press, on_release=on_release) as listener:
            try:
                listener.join()
            except KeyboardInterrupt:
                pass
        self._shutdown()

    def _shutdown(self):
        logger.info("Shutting down JARVIS...")
        self.overlay.stop()
        self.feedback.close()
        BaseExecutor.close()
        BaseExecutor.close()


# ── Entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    orchestrator = JARVISOrchestrator()
    orchestrator.run()
