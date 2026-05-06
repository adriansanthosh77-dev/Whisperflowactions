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


class Signals(QObject):
    update = pyqtSignal(str, str, str)  # icon, text, color


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.signals = Signals()
        self.signals.update.connect(self._apply_update)
        self._init_ui()

    def _init_ui(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 210);
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)

        self.icon_label = QLabel("○")
        self.icon_label.setFont(QFont("SF Pro", 20))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("color: #888888; background: transparent;")

        self.text_label = QLabel("JARVIS ready  [Ctrl+Space]")
        self.text_label.setFont(QFont("SF Mono", 12))
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setStyleSheet("color: #cccccc; background: transparent;")

        self.sub_label = QLabel("")
        self.sub_label.setFont(QFont("SF Mono", 10))
        self.sub_label.setAlignment(Qt.AlignCenter)
        self.sub_label.setStyleSheet("color: #888888; background: transparent;")
        self.sub_label.setMaximumWidth(300)
        self.sub_label.setWordWrap(True)

        layout.addWidget(self.icon_label)
        layout.addWidget(self.text_label)
        layout.addWidget(self.sub_label)
        self.setLayout(layout)
        self.adjustSize()

        # Position: bottom-right corner
        from PyQt5.QtWidgets import QDesktopWidget
        screen = QDesktopWidget().screenGeometry()
        self.move(screen.width() - self.width() - 30, screen.height() - self.height() - 80)

    def _apply_update(self, icon: str, text: str, color: str):
        self.icon_label.setText(icon)
        self.icon_label.setStyleSheet(f"color: {color}; background: transparent;")
        self.text_label.setText(text)
        self.adjustSize()

    def set_sub_text(self, sub: str):
        self.sub_label.setText(sub[:60])
        self.adjustSize()

    def update_state(self, state: State, detail: str = ""):
        cfg = STATE_CONFIG[state]
        self.signals.update.emit(cfg["icon"], cfg["text"], cfg["color"])
        if detail:
            QTimer.singleShot(0, lambda: self.set_sub_text(detail))


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
