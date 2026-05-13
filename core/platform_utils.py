"""
platform_utils.py — Cross-platform PC control abstraction.

Provides a unified API for app launching, volume control, media keys,
window management, system info, and keyboard simulation across Windows, macOS, and Linux.
Auto-detects OS and loads the appropriate implementation.
"""

import os
import sys
import time
import platform
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"
IS_WINDOWS = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"
IS_LINUX = SYSTEM == "Linux"


# ── Platform Detection ──────────────────────────────────────────────

def detect_os() -> str:
    return SYSTEM

def default_browser() -> Optional[str]:
    if IS_WINDOWS:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"HTTP\shell\open\command") as key:
                cmd = winreg.QueryValue(key, "")
                path = cmd.strip().split('"')[1] if '"' in cmd else cmd.split()[0]
                return path
        except Exception:
            pass
        for candidate in ["chrome", "brave", "msedge", "chromium", "firefox"]:
            path = shutil.which(candidate)
            if path:
                return path
    elif IS_MAC:
        for candidate in [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Safari.app/Contents/MacOS/Safari",
        ]:
            if os.path.isfile(candidate):
                return candidate
    elif IS_LINUX:
        for candidate in ["google-chrome", "chromium-browser", "chromium", "firefox"]:
            path = shutil.which(candidate)
            if path:
                return path
    return None


# ── App Launching ───────────────────────────────────────────────────

def launch_app(name_or_path: str) -> bool:
    name = name_or_path.strip().lower()
    try:
        if IS_WINDOWS:
            path = _resolve_windows_app(name)
            if path:
                os.startfile(path)
                return True
            os.startfile(name)
            return True
        elif IS_MAC:
            subprocess.Popen(["open", "-a", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        elif IS_LINUX:
            desktop = shutil.which("gtk-launch") or shutil.which("xdg-open")
            if desktop:
                subprocess.Popen([desktop, name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            path = shutil.which(name)
            if path:
                subprocess.Popen([path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    except Exception as e:
        logger.warning(f"Launch app failed: {e}")
    return False


_APP_ALIASES_WIN = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "cmd.exe",
    "powershell": "powershell.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "brave": "brave.exe",
    "firefox": "firefox.exe",
    "word": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "outlook": "OUTLOOK.EXE",
    "code": "Code.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "discord": "Discord.exe",
    "slack": "Slack.exe",
    "spotify": "Spotify.exe",
    "steam": "steam.exe",
}


def _resolve_windows_app(name: str) -> Optional[str]:
    alias = _APP_ALIASES_WIN.get(name)
    if alias:
        path = shutil.which(alias)
        if path:
            return path
    ext = os.path.splitext(name)[1]
    if ext and ext.lower() in (".exe", ".com", ".bat", ".cmd", ".lnk"):
        path = shutil.which(name)
        if path:
            return path

    # Search common install directories
    search_dirs = [
        Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")),
        Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path(os.environ.get("APPDATA", "")),
    ]
    search_dirs = [d for d in search_dirs if d.exists()]

    exe_name = f"{name}.exe"
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        # Direct match: Program Files\AppName\AppName.exe
        for match in search_dir.rglob(exe_name):
            return str(match)

    # Search Start Menu shortcuts
    start_menu_dirs = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]
    for sm_dir in start_menu_dirs:
        if not sm_dir.exists():
            continue
        for lnk in sm_dir.rglob(f"{name}.lnk"):
            return str(lnk)

    return None


# ── Volume Control ─────────────────────────────────────────────────

def set_volume(level: int) -> bool:
    level = max(0, min(100, level))
    try:
        if IS_WINDOWS:
            return _win_set_volume(level)
        elif IS_MAC:
            subprocess.run(["osascript", "-e", f"set volume output volume {level}"],
                           capture_output=True, timeout=5)
            return True
        elif IS_LINUX:
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                           capture_output=True, timeout=5)
            return True
    except Exception as e:
        logger.warning(f"set_volume failed: {e}")
    return False


def _win_set_volume(level: int) -> bool:
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        return True
    except Exception:
        pass
    try:
        import win32api
        win32api.keybd_event(0xAF, 0, 0, 0)  # VK_VOLUME_UP
        win32api.keybd_event(0xAF, 0, 2, 0)
        return True
    except Exception:
        pass
    return False


def get_volume() -> int:
    try:
        if IS_WINDOWS:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = cast(interface, POINTER(IAudioEndpointVolume))
            return int(volume.GetMasterVolumeLevelScalar() * 100)
    except Exception:
        pass
    return 50


def volume_up(amount: int = 5) -> bool:
    if IS_MAC or IS_LINUX:
        current = get_volume()
        return set_volume(current + amount)
    return _press_virtual_key(0xAF)  # VK_VOLUME_UP


def volume_down(amount: int = 5) -> bool:
    if IS_MAC or IS_LINUX:
        current = get_volume()
        return set_volume(current - amount)
    return _press_virtual_key(0xAE)  # VK_VOLUME_DOWN


def mute() -> bool:
    return _press_virtual_key(0xAD)  # VK_VOLUME_MUTE


# ── Media Keys ──────────────────────────────────────────────────────

def media_play_pause() -> bool:
    return _press_virtual_key(0xB3)  # VK_MEDIA_PLAY_PAUSE


def media_next() -> bool:
    return _press_virtual_key(0xB0)  # VK_MEDIA_NEXT_TRACK


def media_prev() -> bool:
    return _press_virtual_key(0xB1)  # VK_MEDIA_PREV_TRACK


def media_stop() -> bool:
    return _press_virtual_key(0xB2)  # VK_MEDIA_STOP


# ── Keyboard Simulation ─────────────────────────────────────────────

KEY_MAP = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B,
    "space": 0x20, "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "pgup": 0x21, "pgdn": 0x22, "insert": 0x2D, "ins": 0x2D,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "capslock": 0x14, "numlock": 0x90, "scrolllock": 0x91,
    "printscreen": 0x2C, "prtsc": 0x2C, "pause": 0x13,
    "win": 0x5B, "lwin": 0x5B, "rwin": 0x5C,
    "apps": 0x5D, "menu": 0x5D,
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59, "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
}


def _press_virtual_key(vk_code: int) -> bool:
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
            time.sleep(0.03)
            ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)
            time.sleep(0.03)
            return True
        elif IS_MAC:
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to key code {vk_code}'],
                capture_output=True, timeout=5,
            )
            return True
        elif IS_LINUX:
            subprocess.run(["xdotool", "key", f"0x{vk_code:02x}"],
                           capture_output=True, timeout=5)
            return True
    except Exception as e:
        logger.warning(f"Virtual key {vk_code} failed: {e}")
    return False


def send_keys(keys: list[str]) -> bool:
    codes = [KEY_MAP.get(k.lower()) for k in keys]
    codes = [c for c in codes if c]
    if not codes:
        return False
    if IS_WINDOWS:
        import ctypes
        for code in codes:
            ctypes.windll.user32.keybd_event(code, 0, 0, 0)
            time.sleep(0.03)
        for code in reversed(codes):
            ctypes.windll.user32.keybd_event(code, 0, 2, 0)
            time.sleep(0.03)
        return True
    elif IS_MAC:
        for code in codes:
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to key code {code}'],
                capture_output=True, timeout=3,
            )
        return True
    elif IS_LINUX:
        keys_str = "+".join(k.lower() for k in keys if k.lower() in KEY_MAP)
        if keys_str:
            subprocess.run(["xdotool", "key", keys_str], capture_output=True, timeout=3)
            return True
    return False


# ── Window Management ──────────────────────────────────────────────

def get_active_window_title() -> str:
    try:
        if IS_WINDOWS:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        elif IS_MAC:
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first process whose frontmost is true'],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        elif IS_LINUX:
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
    except Exception as e:
        logger.debug(f"get_active_window_title failed: {e}")
    return ""


def minimize_window() -> bool:
    try:
        if IS_WINDOWS:
            send_keys(["win", "down"])
            time.sleep(0.1)
            send_keys(["win", "down"])
            return True
        elif IS_MAC:
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "m" using command down'],
                capture_output=True, timeout=5,
            )
            return True
        elif IS_LINUX:
            subprocess.run(["xdotool", "getactivewindow", "windowminimize"],
                           capture_output=True, timeout=5)
            return True
    except Exception as e:
        logger.warning(f"minimize_window failed: {e}")
    return False


def maximize_window() -> bool:
    try:
        if IS_WINDOWS:
            send_keys(["win", "up"])
            return True
        elif IS_MAC:
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "f" using {command down, control down}'],
                capture_output=True, timeout=5,
            )
            return True
        elif IS_LINUX:
            subprocess.run(["xdotool", "getactivewindow", "windowstate", "--toggle", "fullscreen"],
                           capture_output=True, timeout=5)
            return True
    except Exception as e:
        logger.warning(f"maximize_window failed: {e}")
    return False


def close_window() -> bool:
    try:
        if IS_WINDOWS:
            send_keys(["alt", "f4"])
            return True
        elif IS_MAC:
            subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to keystroke "w" using command down'],
                capture_output=True, timeout=5,
            )
            return True
        elif IS_LINUX:
            send_keys(["alt", "f4"])
            return True
    except Exception as e:
        logger.warning(f"close_window failed: {e}")
    return False


# ── System Info ─────────────────────────────────────────────────────

def get_battery_percent() -> int:
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Battery | Select-Object -ExpandProperty EstimatedChargeRemaining"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                return int(float(result.stdout.strip()))
        elif IS_MAC:
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.splitlines():
                if "%" in line:
                    return int(line.split("%")[0].split()[-1])
        elif IS_LINUX:
            for path in Path("/sys/class/power_supply").glob("BAT*"):
                capacity = (path / "capacity").read_text().strip()
                if capacity:
                    return int(capacity)
    except Exception as e:
        logger.debug(f"get_battery failed: {e}")
    return -1


def get_cpu_usage() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        pass
    try:
        if IS_WINDOWS:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty LoadPercentage"],
                capture_output=True, text=True, timeout=10,
            )
            if result.stdout.strip():
                return float(result.stdout.strip())
        elif IS_MAC:
            result = subprocess.run(
                ["ps", "-A", "-o", "%cpu", "--sort=-%cpu"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.strip().splitlines()[1:]
            if lines:
                return sum(float(l.strip()) for l in lines[:10] if l.strip()) / 10
        elif IS_LINUX:
            result = subprocess.run(
                ["top", "-bn1", "-i"],
                capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "%Cpu(s):" in line:
                    parts = line.split()
                    user = float(parts[1])
                    system = float(parts[3])
                    return user + system
    except Exception as e:
        logger.debug(f"get_cpu failed: {e}")
    return 0.0


# ── Screenshot ─────────────────────────────────────────────────────

def capture_screenshot(path: str = "screenshot.png") -> bool:
    try:
        if IS_WINDOWS:
            try:
                import pyautogui
                pyautogui.screenshot(path)
                return True
            except ImportError:
                pass
            try:
                import mss
                with mss.mss() as sct:
                    sct.shot(output=path)
                return True
            except ImportError:
                pass
            subprocess.run(["powershell", "-NoProfile", "-Command",
                           f"Add-Type -AssemblyName System.Windows.Forms; "
                           f"[System.Windows.Forms.SendKeys]::SendWait('{{PRTSC}}')"],
                          capture_output=True, timeout=5)
            return True
        elif IS_MAC:
            subprocess.run(["screencapture", "-x", path], capture_output=True, timeout=10)
            return True
        elif IS_LINUX:
            for cmd in [["gnome-screenshot", "-f", path],
                        ["import", "-window", "root", path],
                        ["scrot", path]]:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=10)
                    return True
                except FileNotFoundError:
                    continue
    except Exception as e:
        logger.warning(f"Screenshot failed: {e}")
    return False


# ── Process Management ─────────────────────────────────────────────

def kill_process(name: str) -> bool:
    name = name.strip()
    if not name:
        return False
    try:
        if IS_WINDOWS:
            result = subprocess.run(["taskkill", "/F", "/IM", name],
                                    capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        elif IS_MAC:
            result = subprocess.run(["pkill", "-f", name],
                                    capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        elif IS_LINUX:
            result = subprocess.run(["pkill", "-f", name],
                                    capture_output=True, text=True, timeout=10)
            return result.returncode == 0
    except Exception as e:
        logger.warning(f"kill_process failed: {e}")
    return False


def process_running(name: str) -> bool:
    try:
        if IS_WINDOWS:
            result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"],
                                    capture_output=True, text=True, timeout=10)
            return name.lower() in result.stdout.lower()
        elif IS_MAC:
            result = subprocess.run(["pgrep", "-f", name],
                                    capture_output=True, timeout=5)
            return result.returncode == 0
        elif IS_LINUX:
            result = subprocess.run(["pgrep", "-f", name],
                                    capture_output=True, timeout=5)
            return result.returncode == 0
    except Exception:
        return False
