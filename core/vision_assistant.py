import os
import time
import logging

logger = logging.getLogger(__name__)

GRID_AREAS = {
    "top-left":      (0.15, 0.10),
    "top-center":    (0.50, 0.10),
    "top-right":     (0.85, 0.10),
    "middle-left":   (0.15, 0.40),
    "center":        (0.50, 0.40),
    "middle-right":  (0.85, 0.40),
    "bottom-left":   (0.15, 0.75),
    "bottom-center": (0.50, 0.75),
    "bottom-right":  (0.85, 0.75),
}

class VisionAssistant:
    def __init__(self, vision_engine=None):
        self._vision = vision_engine
        self._directml = None
        self._directml_checked = False
        self._screen_width = 1920
        self._screen_height = 1080

    def _ensure_directml(self):
        if self._directml_checked:
            return
        self._directml_checked = True
        try:
            from core.vision_directml import get_directml_vision
            dml = get_directml_vision()
            if dml.is_available():
                self._directml = dml
                logger.info("VisionAssistant: DirectML engine loaded")
        except Exception:
            self._directml = None

    def _get_vision(self):
        if not self._vision:
            from core.vision_engine import get_vision_engine
            self._vision = get_vision_engine()
        return self._vision

    def _update_screen_size(self):
        try:
            import pyautogui
            self._screen_width, self._screen_height = pyautogui.size()
        except ImportError:
            try:
                from core.platform_utils import IS_WINDOWS
                if IS_WINDOWS:
                    import ctypes
                    user32 = ctypes.windll.user32
                    self._screen_width = user32.GetSystemMetrics(0)
                    self._screen_height = user32.GetSystemMetrics(1)
            except Exception:
                pass

    def _grid_to_coords(self, grid_area: str) -> tuple[int, int]:
        frac = GRID_AREAS.get(grid_area, (0.5, 0.5))
        return int(self._screen_width * frac[0]), int(self._screen_height * frac[1])

    def capture_screenshot(self, path: str = "vision_screenshot.png") -> str:
        from core.platform_utils import capture_screenshot
        if capture_screenshot(path):
            return path
        try:
            import pyautogui
            pyautogui.screenshot(path)
            return path
        except ImportError:
            logger.error("No screenshot method available for VisionAssistant")
            return ""

    def describe_screen(self) -> str:
        path = self.capture_screenshot()
        if not path:
            return "Unable to capture screen."
        vision = self._get_vision()
        description = vision.analyze_screenshot(path, "Describe what is on this screen in detail. What applications or elements are visible?")
        return description or "Screen analysis unavailable."

    def find_on_screen(self, target_description: str) -> tuple[int, int] | None:
        self._update_screen_size()
        path = self.capture_screenshot()
        if not path:
            return None

        # Priority 1: OCR — find by text (fast, pixel-perfect)
        try:
            from core.ocr_adapter import find_text_on_screen
            result = find_text_on_screen(target_description, path)
            if result:
                logger.info(f"VisionAssistant: OCR found '{target_description}' at ({result['x']}, {result['y']})")
                return (result["x"], result["y"])
        except Exception as e:
            logger.debug(f"OCR text find failed: {e}")

        # Priority 2: DirectML YOLO — find by object (GPU-accelerated, precise bbox)
        self._ensure_directml()
        if self._directml:
            try:
                obj = self._directml.find_object(path, target_description)
                if obj and "center" in obj:
                    cx, cy = obj["center"]
                    logger.info(f"VisionAssistant: DirectML found '{target_description}' at ({cx}, {cy})")
                    return (cx, cy)
            except Exception as e:
                logger.debug(f"DirectML object find failed: {e}")

        # Priority 3: Moondream visual QA — grid approximation (slow, imprecise)
        vision = self._get_vision()
        prompt = (
            f"Look at this screenshot. Where is '{target_description}' located? "
            f"Answer with exactly one of these grid positions: "
            f"top-left, top-center, top-right, middle-left, center, middle-right, "
            f"bottom-left, bottom-center, bottom-right. "
            f"If not visible, answer 'not found'."
        )
        result = vision.analyze_screenshot(path, prompt)
        if not result or "not found" in result.lower() or "error" in result.lower():
            return None

        for area in GRID_AREAS:
            if area in result.lower():
                return self._grid_to_coords(area)

        return self._grid_to_coords("center")

    def click_on_screen(self, target_description: str) -> bool:
        coords = self.find_on_screen(target_description)
        if not coords:
            logger.warning(f"VisionAssistant: '{target_description}' not found on screen")
            return False

        try:
            import pyautogui
            pyautogui.moveTo(coords[0], coords[1], duration=0.3)
            pyautogui.click()
            logger.info(f"VisionAssistant: Clicked '{target_description}' at {coords}")
            return True
        except ImportError:
            logger.error("pyautogui not installed, cannot click")
            return False

    def type_on_screen(self, target_description: str, text: str) -> bool:
        if not self.click_on_screen(target_description):
            return False
        time.sleep(0.3)
        try:
            import pyautogui
            pyautogui.write(text, interval=0.02)
            return True
        except ImportError:
            logger.error("pyautogui not installed, cannot type")
            return False

    def get_active_window_context(self) -> str:
        from core.platform_utils import get_active_window_title
        title = get_active_window_title()
        screenshot = self.capture_screenshot()
        if not screenshot:
            return f"Active window: {title}. No screenshot available."

        vision = self._get_vision()
        prompt = (
            f"The active window title is '{title}'. "
            f"Based on this screenshot, what is the user doing? "
            f"What elements are visible that the user might interact with?"
        )
        context = vision.analyze_screenshot(screenshot, prompt)
        return context or f"Active window: {title}"

    def detect_objects(self) -> list[dict]:
        """Detect objects on screen using DirectML YOLO (GPU-accelerated)."""
        self._ensure_directml()
        path = self.capture_screenshot()
        if not path or not self._directml:
            return []
        return self._directml.detect_objects(path)


def get_vision_assistant(vision_engine=None):
    return VisionAssistant(vision_engine)
