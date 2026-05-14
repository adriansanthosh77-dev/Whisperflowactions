"""
overlay.py - JARVIS HUD bridge.

Uses the Electron HUD when available and keeps a hidden Tkinter root for the
text command prompt. If Electron cannot launch, falls back to a small Tk HUD.
"""

import asyncio
import atexit
import json
import logging
import os
import queue
import shutil
import signal
import subprocess
import threading
import tkinter as tk
from enum import Enum

import websockets

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    EXECUTING = "executing"
    SUCCESS = "success"
    ERROR = "error"
    SPEAKING = "speaking"


STATE_CONFIG = {
    State.IDLE: {"icon": "O", "text": "JARVIS ready", "color": "#888888"},
    State.LISTENING: {"icon": "*", "text": "Listening...", "color": "#4CAF50"},
    State.THINKING: {"icon": "...", "text": "Thinking...", "color": "#2196F3"},
    State.EXECUTING: {"icon": ">", "text": "Executing...", "color": "#FF9800"},
    State.SUCCESS: {"icon": "OK", "text": "Done", "color": "#00ff88"},
    State.ERROR: {"icon": "!", "text": "Error", "color": "#F44336"},
    State.SPEAKING: {"icon": "V", "text": "Vocalizing", "color": "#ffaa00"},
}


class Overlay:
    def __init__(self):
        self.current_state = State.IDLE
        self.detail = ""
        self.clients = set()
        self.loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._ws_thread = None
        self.root = None
        self.sw = 0
        self.sh = 0
        self._fallback_window = None
        self._electron_process = None
        self._first_wake_done = False

    async def _ws_handler(self, websocket):
        self.clients.add(websocket)
        try:
            await self._send_state(websocket)
            async for _ in websocket:
                pass
        finally:
            self.clients.discard(websocket)

    async def _send_state(self, websocket):
        try:
            # We must assume fullscreen=True on initial connect if state is IDLE/THINKING
            # to prevent the UI from shrinking immediately.
            is_startup = not self._first_wake_done
            await websocket.send(json.dumps({
                "type": "state",
                "state": self.current_state.name,
                "message": self.detail,
                "fullscreen": is_startup
            }))
        except Exception:
            pass

    async def _run_server(self):
        async with websockets.serve(self._ws_handler, "127.0.0.1", 9223):
            self._ready.set()
            await asyncio.Future()

    def _start_server(self):
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._run_server())
        except Exception as e:
            logger.error("HUD WebSocket server error: %s", e)
            self._ready.set()

    def run(self):
        atexit.register(self.stop)

        self._ws_thread = threading.Thread(target=self._start_server, daemon=True)
        self._ws_thread.start()
        self._ready.wait(timeout=5)

        self.root = tk.Tk()
        self.root.withdraw()
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        if not self._launch_electron_hud():
            self._create_tk_fallback()

        self.root.mainloop()

    def _launch_electron_hud(self) -> bool:
        hud_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "hud"))
        if not os.path.isdir(hud_dir):
            logger.warning("Electron HUD folder missing: %s", hud_dir)
            return False

        # Try global electron first, then local node_modules, then cmd wrapper
        electron_exe = shutil.which("electron")
        if electron_exe:
            cmd = [electron_exe, "."]
        else:
            base_node = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "node_modules"))
            electron_exe = os.path.join(base_node, "electron", "dist", "electron.exe")
            if os.path.exists(electron_exe):
                cmd = [electron_exe, "."]
            else:
                electron_cmd = os.path.join(base_node, ".bin", "electron.cmd")
                cmd = [electron_cmd, "."] if os.path.exists(electron_cmd) else ["electron", "."]
        
        logger.info(f"Launching Electron HUD with: {cmd}")

        try:
            creation_flags = 0
            if os.name == 'nt':
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x08000000

            self._electron_process = subprocess.Popen(
                cmd,
                cwd=hud_dir,
                shell=(os.name == 'nt' and not os.path.exists(electron_exe)),
                creationflags=creation_flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            logger.info("Electron HUD launched.")
            return True
        except Exception as e:
            logger.error("Failed to launch Electron HUD: %s", e)
            return False

    @property
    def startup_complete(self) -> bool:
        return self._first_wake_done

    @startup_complete.setter
    def startup_complete(self, value: bool):
        self._first_wake_done = value

    def stop(self):
        logger.info("Stopping HUD...")
        if self._electron_process:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.TerminateProcess(int(self._electron_process._handle), 1)
            except Exception:
                pass
        if self.root:
            try:
                self.root.destroy()
            except:
                pass

    def show_reflexes(self, items: list[str]):
        """Send reflexes list to the HUD."""
        async def broadcast():
            msg = json.dumps({"type": "reflexes", "reflexes": items})
            for client in list(self.clients):
                try:
                    await client.send(msg)
                except Exception:
                    self.clients.discard(client)

        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(), self.loop)

    def _create_tk_fallback(self):
        win = tk.Toplevel(self.root)
        win.title("JARVIS HUD")
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#121212")
        win.geometry(f"250x120+{self.sw-280}+{self.sh-180}")

        frame = tk.Frame(win, bg="#1a1a1a", bd=1, highlightbackground="#333", highlightthickness=1)
        frame.pack(padx=10, pady=10, fill="both", expand=True)
        icon = tk.Label(frame, text="O", font=("Segoe UI", 20, "bold"), fg="#888", bg="#1a1a1a")
        text = tk.Label(frame, text="JARVIS ready", font=("Segoe UI", 12, "bold"), fg="#fff", bg="#1a1a1a")
        sub = tk.Label(frame, text="Hold Shift = voice | Ctrl+Shift+Space = text", font=("Segoe UI", 8), fg="#666", bg="#1a1a1a")
        icon.pack(pady=(8, 0))
        text.pack(pady=2)
        sub.pack(pady=(0, 6))
        self._fallback_window = {"window": win, "icon": icon, "text": text, "sub": sub}
        self._update_tk_fallback(self.current_state, self.detail)

    def _update_tk_fallback(self, state: State, detail: str = ""):
        if not self._fallback_window:
            return
        cfg = STATE_CONFIG[state]
        self._fallback_window["icon"].config(text=cfg["icon"], fg=cfg["color"])
        self._fallback_window["text"].config(text=cfg["text"])
        self._fallback_window["sub"].config(
            text=(detail[:48] if detail else "Hold Shift = voice | Ctrl+Shift+Space = text"),
            fg=("#aaa" if detail else "#666"),
        )

    def set_state(self, state: State, detail: str = "", fullscreen: bool = False):
        self.current_state = state
        self.detail = detail
        if self.root:
            self.root.after(0, lambda: self._update_tk_fallback(state, detail))

        async def broadcast():
            msg = json.dumps({
                "type": "state", 
                "state": state.name, 
                "message": detail, # HUD expects 'message'
                "fullscreen": fullscreen
            })
            for client in list(self.clients):
                try:
                    await client.send(msg)
                except Exception:
                    self.clients.discard(client)

        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(), self.loop)

    def set_audio_energy(self, energy: float):
        """Broadcast audio energy level for the visualizer."""
        async def broadcast():
            msg = json.dumps({"type": "audio_energy", "energy": energy}) # Match index.html
            for client in list(self.clients):
                try:
                    await client.send(msg)
                except Exception:
                    self.clients.discard(client)

        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(), self.loop)

    def prompt_text(self, title: str = "Command JARVIS:", default_value: str = "") -> str:
        if not self.root:
            logger.error("Overlay root not initialized; cannot prompt.")
            return None

        result_queue = queue.Queue()

        def _create_dialog():
            try:
                dialog = tk.Toplevel(self.root)
                dialog.overrideredirect(True)
                dialog.attributes("-topmost", True)
                dialog.configure(bg="#1a1a1a", bd=2, highlightbackground="#4CAF50", highlightthickness=1)

                dw, dh = 450, 80
                dialog.geometry(f"{dw}x{dh}+{(self.sw-dw)//2}+{(self.sh-dh)//2}")

                lbl = tk.Label(dialog, text=title, font=("Segoe UI", 10, "bold"), fg="#4CAF50", bg="#1a1a1a")
                lbl.pack(pady=(10, 2), padx=10, anchor="w")

                entry = tk.Entry(dialog, font=("Segoe UI", 12), bg="#222", fg="#fff", insertbackground="#fff", bd=0, highlightthickness=1, highlightbackground="#444")
                entry.insert(0, default_value)
                entry.pack(fill="x", padx=10, pady=5)
                entry.focus_set()
                entry.selection_range(0, tk.END)

                def _close(val):
                    result_queue.put(val)
                    dialog.destroy()

                entry.bind("<Return>", lambda e: _close(entry.get()))
                entry.bind("<Escape>", lambda e: _close(None))
                
                # Force focus
                dialog.after(100, lambda: dialog.focus_force())
                dialog.after(110, lambda: entry.focus_set())
                
            except Exception as e:
                logger.error(f"Failed to create prompt dialog: {e}")
                result_queue.put(None)

        self.root.after(0, _create_dialog)
        
        # Wait for result with a timeout to prevent permanent hang
        try:
            return result_queue.get(timeout=60.0) 
        except queue.Empty:
            logger.warning("Prompt text timed out after 60s")
            return None


    def prompt_blocked(self, title: str, description: str, timeout: float = 300) -> bool:
        if not self.root:
            logger.error("Overlay root not initialized; cannot prompt blocked.")
            return False

        result_queue = queue.Queue()

        def _create_dialog():
            try:
                dw, dh = 520, 200
                dialog = tk.Toplevel(self.root)
                dialog.overrideredirect(True)
                dialog.attributes("-topmost", True)
                dialog.configure(bg="#1a1a1a", bd=2, highlightbackground="#F44336", highlightthickness=2)
                dialog.geometry(f"{dw}x{dh}+{(self.sw-dw)//2}+{(self.sh-dh)//2}")

                tk.Label(dialog, text=title, font=("Segoe UI", 14, "bold"),
                         fg="#F44336", bg="#1a1a1a").pack(pady=(16, 4), padx=16, anchor="w")

                tk.Label(dialog, text=description, font=("Segoe UI", 10),
                         fg="#ccc", bg="#1a1a1a", wraplength=480, justify="left"
                         ).pack(pady=4, padx=16, anchor="w")

                btn_frame = tk.Frame(dialog, bg="#1a1a1a")
                btn_frame.pack(pady=(16, 12))

                def _done():
                    result_queue.put(True)
                    dialog.destroy()

                def _cancel():
                    result_queue.put(False)
                    dialog.destroy()

                tk.Button(btn_frame, text="I've handled it — Continue",
                          font=("Segoe UI", 11), bg="#4CAF50", fg="white",
                          bd=0, padx=20, pady=6, cursor="hand2",
                          command=_done).pack(side="left", padx=6)

                tk.Button(btn_frame, text="Abort",
                          font=("Segoe UI", 11), bg="#555", fg="white",
                          bd=0, padx=20, pady=6, cursor="hand2",
                          command=_cancel).pack(side="left", padx=6)

                dialog.after(100, lambda: dialog.focus_force())
            except Exception as e:
                logger.error(f"Failed to create blocked dialog: {e}")
                result_queue.put(False)

        self.root.after(0, _create_dialog)

        try:
            return result_queue.get(timeout=timeout)
        except queue.Empty:
            logger.warning("Blocked prompt timed out")
            return False


def run_overlay_in_thread() -> Overlay:
    overlay = Overlay()
    thread = threading.Thread(target=overlay.run, daemon=True)
    thread.start()
    overlay._ready.wait(timeout=5)

    # Ensure Electron is killed when Python exits (console close, Ctrl+C, etc.)
    import atexit
    import signal
    atexit.register(lambda o=overlay: o.stop())
    signal.signal(signal.SIGTERM, lambda *_: overlay.stop())
    signal.signal(signal.SIGINT, lambda *_: overlay.stop())

    return overlay
