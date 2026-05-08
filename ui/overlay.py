"""
overlay.py — Floating HUD overlay using PyQt5.

Shows:  ● Listening...  |  🔍 Intent detected  |  ✓ Done  |  ✗ Error

Runs in its own thread. Main thread calls update_state() to change display.
"""

import sys
import threading
from enum import Enum
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QColor

app: QApplication = None


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

HINTS = [
    "Hold Ctrl+Space to talk",
    "Say 'Switch to [Agent]' to swap expert",
    "Say 'Switch to default' to reset",
    "Say 'Save agent as [Name]' to create expert",
    "Press ESC to abort anytime"
]


class Signals(QObject):
    update = pyqtSignal(str, str, str)  # icon, text, color


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = Signals()
        self.signals.update.connect(self._apply_update)
        self._init_ui()
        self._hint_index = 0
        self._hint_timer = QTimer(self)
        self._hint_timer.timeout.connect(self._next_hint)
        self._hint_timer.start(5000) # every 5s

    def _next_hint(self):
        if self._current_state == State.IDLE:
            self._hint_index = (self._hint_index + 1) % len(HINTS)
            self.set_sub_text(HINTS[self._hint_index])

    def _init_ui(self):
        self._current_state = State.IDLE
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 210);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self.icon_label = QLabel("○")
        self.icon_label.setFont(QFont("SF Pro Display", 22, QFont.Bold))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("color: #888888; background: transparent; border: none;")

        self.text_label = QLabel("JARVIS ready")
        self.text_label.setFont(QFont("SF Pro Text", 13, QFont.Medium))
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("color: #ffffff; background: transparent; border: none;")

        self.sub_label = QLabel(HINTS[0])
        self.sub_label.setFont(QFont("SF Pro Text", 9))
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setStyleSheet("color: #999999; background: transparent; border: none;")
        self.sub_label.setMaximumWidth(280)
        self.sub_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addWidget(self.sub_label)
        self.setLayout(layout)
        self.setMinimumWidth(220)
        self.adjustSize()

        # Position: bottom-right corner
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        self.move(screen.width() - self.width() - 30, screen.height() - self.height() - 80)

    def _apply_update(self, icon: str, text: str, color: str):
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent; border: none;")
        self.text_label.setText(text)
        self.adjustSize()

    def set_sub_text(self, sub: str):
        self.sub_label.setText(sub[:120])
        self.adjustSize()

    def update_state(self, state: State, detail: str = ""):
        self._current_state = state
        cfg = STATE_CONFIG[state]
        self.signals.update.emit(cfg["icon"], cfg["text"], cfg["color"])
        
        # If we have a detail, show it. Otherwise if IDLE, show hints.
        if detail:
            QTimer.singleShot(0, lambda: self.set_sub_text(detail))
        elif state == State.IDLE:
            QTimer.singleShot(0, lambda: self.set_sub_text(HINTS[self._hint_index]))
        else:
            QTimer.singleShot(0, lambda: self.set_sub_text(""))


class Overlay:
    """Thread-safe wrapper. Call from any thread."""

    def __init__(self):
        global app
        if not QApplication.instance():
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        self.window = OverlayWindow()
        self.window.show()

    def set_state(self, state: State, detail: str = ""):
        self.window.update_state(state, detail)

    def run(self):
        """Block — call from main thread (or dedicated Qt thread)."""
        app.exec_()


def run_overlay_in_thread() -> Overlay:
    """Launch overlay in a background thread. Returns overlay handle."""
    overlay = None
    ready = threading.Event()

    def _run():
        nonlocal overlay
        overlay = Overlay()
        ready.set()
        overlay.run()

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    ready.wait(timeout=5)
    return overlay
