"""
overlay.py — Floating HUD overlay using Tkinter (Zero-Dependency).
Supports Voice HUD and Text Input Prompt.
"""

import tkinter as tk
import threading
import queue
import logging
from enum import Enum

logger = logging.getLogger(__name__)

class State(Enum):
    IDLE      = "idle"
    LISTENING = "listening"
    THINKING  = "thinking"
    EXECUTING = "executing"
    SUCCESS   = "success"
    ERROR     = "error"

STATE_CONFIG = {
    State.IDLE:      {"icon": "○", "text": "JARVIS ready",   "color": "#888888"},
    State.LISTENING: {"icon": "●", "text": "Listening...",   "color": "#4CAF50"},
    State.THINKING:  {"icon": "◌", "text": "Thinking...",    "color": "#2196F3"},
    State.EXECUTING: {"icon": "▶", "text": "Executing...",   "color": "#FF9800"},
    State.SUCCESS:   {"icon": "✓", "text": "Done",           "color": "#4CAF50"},
    State.ERROR:     {"icon": "✗", "text": "Error",          "color": "#F44336"},
}

class OverlayWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("JARVIS HUD")
        self.root.overrideredirect(True) 
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "#121212")
        self.root.configure(bg="#121212")

        # Container
        self.frame = tk.Frame(self.root, bg="#1a1a1a", bd=1, highlightbackground="#333", highlightthickness=1)
        self.frame.pack(padx=10, pady=10, fill="both", expand=True)

        self.icon_label = tk.Label(self.frame, text="○", font=("Segoe UI", 24, "bold"), fg="#888", bg="#1a1a1a")
        self.icon_label.pack(pady=(5, 0))

        self.text_label = tk.Label(self.frame, text="JARVIS ready", font=("Segoe UI", 12, "bold"), fg="#fff", bg="#1a1a1a")
        self.text_label.pack(pady=2)

        self.sub_label = tk.Label(self.frame, text="Ctrl+Space: Voice | Ctrl+Shift+Space: Text", font=("Segoe UI", 8), fg="#666", bg="#1a1a1a")
        self.sub_label.pack(pady=(0, 5))

        self.w, self.h = 240, 120
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.w}x{self.h}+{self.sw-self.w-30}+{sh-h-80}" if 'sh' in locals() else f"{self.w}x{self.h}+{self.sw-self.w-30}+{self.root.winfo_screenheight()-self.h-80}")

    def update_state(self, state: State, detail: str = ""):
        cfg = STATE_CONFIG[state]
        self.icon_label.config(text=cfg["icon"], fg=cfg["color"])
        self.text_label.config(text=cfg["text"])
        if detail:
            self.sub_label.config(text=detail[:45], fg="#aaa")
        else:
            self.sub_label.config(text="Ctrl+Space: Voice | Ctrl+Shift+Space: Text", fg="#666")

    def prompt_text(self) -> str:
        result = {"text": None}
        dialog = tk.Toplevel(self.root)
        dialog.overrideredirect(True)
        dialog.attributes("-topmost", True)
        dialog.configure(bg="#1a1a1a", bd=2, highlightbackground="#4CAF50", highlightthickness=1)
        
        dw, dh = 450, 80
        dialog.geometry(f"{dw}x{dh}+{(self.sw-dw)//2}+{(self.root.winfo_screenheight()-dh)//2}")
        
        lbl = tk.Label(dialog, text="Command JARVIS:", font=("Segoe UI", 10, "bold"), fg="#4CAF50", bg="#1a1a1a")
        lbl.pack(pady=(10, 2), padx=10, anchor="w")
        
        entry = tk.Entry(dialog, font=("Segoe UI", 12), bg="#222", fg="#fff", insertbackground="#fff", bd=0, highlightthickness=1, highlightbackground="#444")
        entry.pack(fill="x", padx=10, pady=5)
        entry.focus_set()
        
        def _submit(event=None):
            result["text"] = entry.get()
            dialog.destroy()
        def _cancel(event=None):
            dialog.destroy()

        entry.bind("<Return>", _submit)
        entry.bind("<Escape>", _cancel)
        self.root.wait_window(dialog)
        return result["text"]

class Overlay:
    def __init__(self):
        self.window = None
        self._ready = threading.Event()

    def run(self):
        self.window = OverlayWindow()
        self._ready.set()
        self.window.root.mainloop()

    def set_state(self, state: State, detail: str = ""):
        if self.window:
            self.window.root.after(0, lambda: self.window.update_state(state, detail))

    def prompt_text(self) -> str:
        if not self.window: return None
        q = queue.Queue()
        self.window.root.after(0, lambda: q.put(self.window.prompt_text()))
        return q.get()

def run_overlay_in_thread() -> Overlay:
    overlay = Overlay()
    t = threading.Thread(target=overlay.run, daemon=True)
    t.start()
    overlay._ready.wait(timeout=5)
    return overlay
