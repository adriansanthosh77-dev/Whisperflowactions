import logging
import threading
import pystray
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

class TrayIcon:
    def __init__(self, on_show=None, on_quit=None, on_toggle_listen=None):
        self._on_show = on_show
        self._on_quit = on_quit
        self._on_toggle_listen = on_toggle_listen
        self._icon = None

    def _create_image(self):
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([8, 8, 56, 56], fill="#4CAF50")
        draw.text((16, 14), "J", fill="white", font=None)
        return img

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Show JARVIS", lambda: self._call(self._on_show)),
            pystray.MenuItem("Toggle Listening", lambda: self._call(self._on_toggle_listen)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda: self._call(self._on_quit)),
        )
        self._icon = pystray.Icon("jarvis", self._create_image(), "JARVIS", menu)
        self._icon.run()

    def stop(self):
        if self._icon:
            self._icon.stop()

    def _call(self, fn):
        if fn:
            fn()

def run_tray_in_thread(on_show=None, on_quit=None, on_toggle_listen=None) -> TrayIcon:
    tray = TrayIcon(on_show, on_quit, on_toggle_listen)
    t = threading.Thread(target=tray.run, daemon=True)
    t.start()
    return tray
