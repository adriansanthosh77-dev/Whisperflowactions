"""
pc_executor.py - Guarded local PC controls for JARVIS.

This executor handles safe desktop actions directly and refuses actions that
should not be automated without a stronger explicit policy.
"""

import os
import time
import glob
import ctypes
import logging
import re
import shutil
import subprocess
import requests
from pathlib import Path
from typing import Iterable

import pyperclip

from models.intent_schema import IntentResult, Context, ExecutionResult
from core.platform_utils import (
    IS_WINDOWS, IS_MAC, IS_LINUX,
    launch_app as platform_launch,
    send_keys as platform_keys,
    get_battery_percent as platform_battery,
    get_cpu_usage as platform_cpu,
    capture_screenshot as platform_screenshot,
    kill_process as platform_kill,
    volume_up as platform_vol_up,
    volume_down as platform_vol_down,
    mute as platform_mute,
    media_play_pause as platform_play,
    media_next as platform_next,
    media_prev as platform_prev,
    minimize_window as platform_minimize,
    maximize_window as platform_maximize,
    close_window as platform_close,
)

logger = logging.getLogger(__name__)

FORBIDDEN_OPERATIONS = {"shell", "install"}
CONFIRM_OPERATIONS = {"delete", "kill", "rename_file"}
SAFE_OPERATIONS = {
    "launch_app", "open_file", "find_file", "copy", "paste", "type", "press",
    "hotkey", "screenshot", "close_tab", "close_window", "switch_window",
    "minimize_window", "maximize_window", "snap_left", "snap_right", "new_tab",
    "reopen_closed_tab", "duplicate_tab", "next_tab", "prev_tab", "reload",
    "hard_reload", "browser_back", "browser_forward", "focus_address_bar",
    "zoom_in", "zoom_out", "zoom_reset", "inspect_element", "open_console",
    "show_history", "show_bookmarks", "show_downloads", "open_incognito",
    "copy_current_url", "find_on_page", "media_play_pause", "media_next", "media_previous",
    "volume_up", "volume_down", "volume_mute", "fullscreen",
    "undo", "redo", "select_all", "save_file", "text_bold", "text_italic",
    "open_desktop", "open_downloads", "open_documents", "open_pictures", "open_videos",
    "open_music", "open_recent", "open_task_manager", "open_settings", "lock_pc",
    "scroll_down", "scroll_up", "page_down", "page_up", "go_to_top", "go_to_bottom",
    "brightness_up", "brightness_down", "wait", "chat_reflex",
    "get_battery_status", "get_current_time", "get_system_health", "get_current_date",
    "get_current_user", "get_ip_address", "get_screen_resolution",
    "empty_recycle_bin", "break_timer", "toggle_night_light", "toggle_focus_assist",
}

APP_COMMANDS = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "powershell": "powershell.exe",
    "chrome": "chrome.exe",
    "edge": "msedge.exe",
    "brave": "brave.exe",
    "brave browser": "brave.exe",
    "vscode": "code",
    "vs code": "code",
    "visual studio code": "code",
    "explorer": "explorer.exe",
    "discord": "discord.exe",
    "spotify": "spotify.exe",
    "slack": "slack.exe",
    "whatsapp": "WhatsApp.exe",
    "telegram": "Telegram.exe",
    "teams": "ms-teams:",
    "zoom": "zoom.exe",
    "steam": "steam.exe",
    "epicgames": "com.epicgames.launcher:",
    "camera": "microsoft.windows.camera:",
    "devmgmt.msc": "devmgmt.msc",
    "regedit": "regedit.exe",
    "cleanmgr": "cleanmgr.exe",
    "resmon": "resmon.exe",
    "control": "control.exe",
}



SAFE_DIRS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
]


class PCExecutor:
    def execute(self, intent: IntentResult, context: Context) -> tuple[bool, str]:
        op = intent.data.get("operation") or intent.intent
        safety = intent.data.get("safety_level", "safe")
        if op in FORBIDDEN_OPERATIONS or safety == "forbidden":
            return False, f"Refused forbidden PC action: {op}"
        if op not in SAFE_OPERATIONS and op not in CONFIRM_OPERATIONS:
            # Check plugin operations before rejecting
            from core.plugin_manager import get_plugin_manager
            if not get_plugin_manager().get_operation_handler(op):
                return False, f"Refused unknown PC action: {op}"
        if op in CONFIRM_OPERATIONS and safety != "confirm":
            return False, f"Refused guarded PC action without confirmation policy: {op}"

        try:
            if op == "rename_file":
                return self._rename_item(intent).as_tuple()
            if op == "launch_app":
                return self._launch_app(intent).as_tuple()
            if op == "open_file":
                return self._open_file(intent).as_tuple()
            if op == "find_file":
                return self._find_file(intent).as_tuple()
            if op == "copy":
                return self._copy(intent).as_tuple()
            if op == "paste":
                return self._paste(intent).as_tuple()
            if op == "type":
                return self._type_text(intent).as_tuple()
            if op == "press":
                return self._press(intent.data.get("key") or intent.target).as_tuple()
            if op == "hotkey":
                return self._hotkey(intent.data.get("keys", [])).as_tuple()
            if op == "screenshot":
                return self._screenshot().as_tuple()
            if op == "close_tab":
                return self._hotkey(["ctrl", "w"], "Closed current tab.").as_tuple()
            if op == "close_window":
                platform_close()
                return ExecutionResult(True, "Closed current window.").as_tuple()
            if op == "switch_window":
                target = intent.target or intent.data.get("target") or ""
                if target:
                    return self._switch_to_window(target).as_tuple()
                return self._hotkey(["alt", "tab"], "Switched window.").as_tuple()
            if op == "minimize_window":
                platform_minimize()
                return ExecutionResult(True, "Minimized current window.").as_tuple()
            if op == "maximize_window":
                platform_maximize()
                return ExecutionResult(True, "Maximized current window.").as_tuple()
            if op == "snap_left":
                return self._hotkey(["win", "left"], "Snapped window left.").as_tuple()
            if op == "snap_right":
                return self._hotkey(["win", "right"], "Snapped window right.").as_tuple()
            if op == "new_tab":
                return self._hotkey(["ctrl", "t"], "Opened new tab.").as_tuple()
            if op == "reopen_closed_tab":
                return self._hotkey(["ctrl", "shift", "t"], "Reopened closed tab.").as_tuple()
            if op == "duplicate_tab":
                self._hotkey(["ctrl", "l"])
                time.sleep(0.05)
                return self._hotkey(["alt", "enter"], "Duplicated current tab.").as_tuple()
            if op == "next_tab":
                return self._hotkey(["ctrl", "tab"], "Switched to next tab.").as_tuple()
            if op == "prev_tab":
                return self._hotkey(["ctrl", "shift", "tab"], "Switched to previous tab.").as_tuple()
            if op == "reload":
                return self._hotkey(["ctrl", "r"], "Reloaded page.").as_tuple()
            if op == "hard_reload":
                return self._hotkey(["ctrl", "f5"], "Hard reloaded page.").as_tuple()
            if op == "browser_back":
                return self._hotkey(["alt", "left"], "Went back.").as_tuple()
            if op == "browser_forward":
                return self._hotkey(["alt", "right"], "Went forward.").as_tuple()
            if op == "focus_address_bar":
                return self._hotkey(["ctrl", "l"], "Focused address bar.").as_tuple()
            if op == "zoom_in":
                return self._hotkey(["ctrl", "plus"], "Zoomed in.").as_tuple()
            if op == "zoom_out":
                return self._hotkey(["ctrl", "minus"], "Zoomed out.").as_tuple()
            if op == "zoom_reset":
                return self._hotkey(["ctrl", "0"], "Reset zoom.").as_tuple()
            if op == "inspect_element":
                return self._press("f12").as_tuple()
            if op == "open_console":
                return self._hotkey(["ctrl", "shift", "j"], "Opened browser console.").as_tuple()
            if op == "show_history":
                return self._hotkey(["ctrl", "h"], "Opened browser history.").as_tuple()
            if op == "show_bookmarks":
                return self._hotkey(["ctrl", "shift", "o"], "Opened bookmarks.").as_tuple()
            if op == "show_downloads":
                return self._hotkey(["ctrl", "j"], "Opened downloads.").as_tuple()
            if op == "open_incognito":
                return self._hotkey(["ctrl", "shift", "n"], "Opened private window.").as_tuple()
            if op == "copy_current_url":
                return self._copy_current_url().as_tuple()
            if op == "find_on_page":
                return self._find_on_page(intent).as_tuple()
            if op in ("media_play_pause", "media_next", "media_previous", "volume_up", "volume_down", "volume_mute"):
                return self._press(op).as_tuple()
            if op == "fullscreen":
                return self._press("f11").as_tuple()
            if op == "undo":
                return self._hotkey(["ctrl", "z"], "Undid last action.").as_tuple()
            if op == "redo":
                return self._hotkey(["ctrl", "y"], "Redid last action.").as_tuple()
            if op == "select_all":
                return self._hotkey(["ctrl", "a"], "Selected all.").as_tuple()
            if op == "save_file":
                return self._hotkey(["ctrl", "s"], "Saved.").as_tuple()
            if op == "text_bold":
                return self._hotkey(["ctrl", "b"], "Toggled bold.").as_tuple()
            if op == "text_italic":
                return self._hotkey(["ctrl", "i"], "Toggled italic.").as_tuple()
            if op in ("open_desktop", "open_downloads", "open_documents", "open_pictures", "open_videos", "open_music", "open_recent"):
                return self._open_known_folder(op).as_tuple()
            if op == "open_task_manager":
                return self._hotkey(["ctrl", "shift", "escape"], "Opened Task Manager.").as_tuple()
            if op == "open_settings":
                return self._open_settings(intent).as_tuple()
            if op == "lock_pc":
                return self._hotkey(["win", "l"], "Locked the PC.").as_tuple()
            if op in ("scroll_down", "page_down"):
                return self._press("pagedown").as_tuple()
            if op in ("scroll_up", "page_up"):
                return self._press("pageup").as_tuple()
            if op == "go_to_top":
                return self._press("home").as_tuple()
            if op == "go_to_bottom":
                return self._press("end").as_tuple()
            if op in ("brightness_up", "brightness_down"):
                delta = 10 if op == "brightness_up" else -10
                return self._adjust_brightness(delta).as_tuple()
            if op == "wait":
                seconds = min(float(intent.data.get("seconds", 1)), 10.0)
                time.sleep(seconds)
                return True, f"Waited {seconds:g} seconds."
            if op == "delete":
                return self._delete_file(intent).as_tuple()
            if op == "kill":
                return self._kill_process(intent).as_tuple()
            if op == "shell":
                return self._run_shell(intent).as_tuple()
            if op == "chat_reflex":
                return self._chat_reflex(intent).as_tuple()
            if op == "get_battery_status":
                return self._get_battery_status().as_tuple()
            if op == "get_current_time":
                return self._get_current_time().as_tuple()
            if op == "get_current_date":
                return self._get_current_date().as_tuple()
            if op == "get_system_health":
                return self._get_system_health().as_tuple()
            if op == "get_current_user":
                return self._get_current_user().as_tuple()
            if op == "get_ip_address":
                return self._get_ip_address().as_tuple()
            if op == "get_screen_resolution":
                return self._get_screen_resolution().as_tuple()
            if op == "empty_recycle_bin":
                return self._empty_recycle_bin().as_tuple()
            if op == "break_timer":
                return self._break_timer().as_tuple()
            if op == "toggle_night_light":
                return self._toggle_night_light().as_tuple()
            if op == "toggle_focus_assist":
                return self._toggle_focus_assist().as_tuple()
            # Check plugin operations
            from core.plugin_manager import get_plugin_manager
            plugin_handler = get_plugin_manager().get_operation_handler(op)
            if plugin_handler:
                return plugin_handler(intent, context)
            return False, f"Unknown PC action: {op}"
        except Exception as e:
            logger.exception("PC action failed: %s", e)
            return False, f"PC action failed: {str(e)[:100]}"

    def _chat_reflex(self, intent: IntentResult) -> ExecutionResult:
        mode = intent.data.get("mode", "draft")
        text = intent.data.get("text", "")
        if not text:
            return ExecutionResult(False, "No text provided for chat reflex.")

        prompts = {
            "reply": "Draft a short, natural response to the following message. Output only the reply text, no quotes.",
            "correct": "Correct the grammar and spelling of the following text. Output ONLY the corrected text, no quotes or preamble.",
            "draft": "Draft a concise message based on the following instruction. Output only the drafted text.",
        }
        sys_prompt = prompts.get(mode, prompts["draft"])
        
        # Use simple one-shot LLM call
        try:
            processed_text = self._llm_process(sys_prompt, text)
            if not processed_text:
                return ExecutionResult(False, "LLM failed to process the chat reflex.")
            
            # Type the result
            self._type_text_direct(processed_text)
            return ExecutionResult(True, f"Reflex ({mode}) completed.")
        except Exception as e:
            return ExecutionResult(False, f"Chat reflex failed: {e}")

    def _llm_process(self, system: str, user: str) -> str:
        """Call the configured LLM (OpenAI or Ollama) for a quick reflex processing."""
        provider = os.getenv("LLM_PROVIDER", "ollama").lower()
        if provider == "openai" and os.getenv("OPENAI_API_KEY"):
            url = "https://api.openai.com/v1/chat/completions"
            headers = {"Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}"}
            payload = {
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 500,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip().strip('"')
        
        # Fallback to Ollama
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "llama3")
        try:
            import requests as http_requests
            resp = http_requests.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.2}
                },
                timeout=20
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "").strip().strip('"')
        except Exception:
            return ""

    def _type_text_direct(self, text: str):
        """Type text into active app with clipboard save/restore and char-by-char fallback."""
        original = None
        try:
            original = pyperclip.paste()
        except Exception:
            pass
        try:
            pyperclip.copy(text)
            time.sleep(0.05)
            self._tap_keys(["ctrl", "v"])
            time.sleep(0.05)
        except Exception:
            self._type_char_by_char(text)
        finally:
            if original is not None:
                try:
                    pyperclip.copy(original)
                except Exception:
                    pass

    def _type_char_by_char(self, text: str):
        """Fallback: type text char by char using pynput (works in any app)."""
        from pynput.keyboard import Key, Controller as KbController
        kb = KbController()
        for char in text:
            try:
                if char == "\n":
                    kb.press(Key.enter)
                    kb.release(Key.enter)
                else:
                    kb.press(char)
                    kb.release(char)
            except Exception:
                pass
            time.sleep(0.003)

    def _get_explorer_selection(self) -> list[str]:
        if not IS_WINDOWS:
            return []
        try:
            import comtypes.client
            import pythoncom
            pythoncom.CoInitialize()
            shell = comtypes.client.CreateObject("Shell.Application")
            windows = shell.Windows()
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            for i in range(windows.Count):
                window = windows.Item(i)
                if window and int(window.hwnd) == hwnd:
                    selection = window.Document.SelectedItems()
                    items = [item.Path for item in selection]
                    return items
        except Exception as e:
            logger.debug(f"Explorer selection failed: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        return []

    def _rename_item(self, intent: IntentResult) -> ExecutionResult:
        new_name = intent.data.get("new_name") or intent.target
        if not new_name: return ExecutionResult(False, "No new name provided.")
        
        selection = self._get_explorer_selection()
        if not selection:
            return ExecutionResult(False, "No file selected in Explorer. Please click a file first.")
        
        old_path = Path(selection[0])
        # Preserve extension if not provided
        if "." not in new_name and old_path.suffix:
            new_name += old_path.suffix
            
        new_path = old_path.parent / new_name
        try:
            old_path.rename(new_path)
            return ExecutionResult(True, f"Renamed to {new_name}")
        except Exception as e:
            return ExecutionResult(False, f"Rename failed: {e}")

    def _delete_file(self, intent: IntentResult) -> ExecutionResult:
        target = intent.target or intent.data.get("path") or intent.data.get("file") or ""
        path = self._resolve_path(target)
        if not path or not path.exists():
            return ExecutionResult(False, f"Could not find file to delete: {target}")
        
        # Safety check: Only allow deleting in SAFE_DIRS for now
        is_safe = any(str(path.resolve()).startswith(str(root.resolve())) for root in SAFE_DIRS)
        if not is_safe:
            return ExecutionResult(False, f"Deletion restricted: {path} is outside of safe user directories.")

        try:
            if path.is_file():
                os.remove(path)
            else:
                import shutil
                shutil.rmtree(path)
            return ExecutionResult(True, f"Deleted {path.name}.")
        except Exception as e:
            return ExecutionResult(False, f"Delete failed: {e}")

    def _kill_process(self, intent: IntentResult) -> ExecutionResult:
        target = (intent.target or intent.app or "").lower()
        if not target:
            return ExecutionResult(False, "No process specified to kill.")

        target = target.strip().strip('"')
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", target):
            return ExecutionResult(False, f"Invalid process name: {target}")
        if IS_WINDOWS and not target.endswith(".exe"):
            target += ".exe"

        if platform_kill(target):
            return ExecutionResult(True, f"Killed process {target}.")
        return ExecutionResult(False, f"Failed to kill {target}.")

    def _run_shell(self, intent: IntentResult) -> ExecutionResult:
        return ExecutionResult(False, "Shell execution is forbidden in JARVIS safe mode.")

    def _launch_app(self, intent: IntentResult) -> ExecutionResult:
        app = (intent.data.get("app") or intent.target or intent.app or "").strip().lower()
        if app == "pc":
             app = (intent.target or "").strip().lower()

        url = intent.data.get("url")

        # No specific app + URL → open in default browser
        if not app and url:
            import webbrowser
            webbrowser.open(url)
            return ExecutionResult(True, f"Opened {url} in default browser.")

        if app.startswith("ms-settings:") and IS_WINDOWS:
            os.startfile(app)
            return ExecutionResult(True, f"Opened {app}.")

        if app.startswith("shell:") and IS_WINDOWS:
            os.startfile(app)
            return ExecutionResult(True, f"Opened {app}.")

        if platform_launch(app):
            if url:
                import webbrowser
                webbrowser.open(url)
                return ExecutionResult(True, f"Opened {url} in {app}.")
            return ExecutionResult(True, f"Launched {app}.")

        cmd = APP_COMMANDS.get(app)
        if not cmd:
            return ExecutionResult(False, f"Unknown app '{app}'.")

        try:
            if str(cmd).endswith(":"):
                if IS_WINDOWS:
                    os.startfile(cmd)
                elif IS_MAC:
                    subprocess.Popen(["open", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return ExecutionResult(True, f"Launched {app}.")
            subprocess.Popen([cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ExecutionResult(True, f"Launched {app}.")
        except Exception as e:
            return ExecutionResult(False, f"Failed to launch {app}: {e}")

    def _open_file(self, intent: IntentResult) -> ExecutionResult:
        target = intent.target or intent.data.get("path") or intent.data.get("file") or ""
        path = self._resolve_path(target)
        if not path:
            return ExecutionResult(False, f"Could not find file or folder: {target}")
        os.startfile(str(path))
        return ExecutionResult(True, f"Opened {path.name}.", observed_state={"path": str(path)})

    def _find_file(self, intent: IntentResult) -> ExecutionResult:
        query = intent.target or intent.data.get("query") or ""
        matches = self._find_matches(query)
        if not matches:
            return ExecutionResult(False, f"No file found for: {query}")
        
        # Open the first match for instant access
        best_match = matches[0]
        os.startfile(str(best_match))
        
        names = ", ".join(p.name for p in matches[:5])
        return ExecutionResult(True, f"Found and opened: {best_match.name}", observed_state={"matches": [str(p) for p in matches[:10]]})

    def _copy(self, intent: IntentResult) -> ExecutionResult:
        text = intent.data.get("text") or intent.target
        if text:
            pyperclip.copy(text)
            return ExecutionResult(True, "Copied text to clipboard.")
        return self._hotkey(["ctrl", "c"], "Copied selection.")

    def _paste(self, intent: IntentResult) -> ExecutionResult:
        text = intent.data.get("text") or intent.target
        if text:
            pyperclip.copy(text)
        return self._hotkey(["ctrl", "v"], "Pasted clipboard.")

    def _copy_current_url(self) -> ExecutionResult:
        self._hotkey(["ctrl", "l"])
        time.sleep(0.05)
        self._hotkey(["ctrl", "c"])
        return ExecutionResult(True, "Copied current URL.")

    def _find_on_page(self, intent: IntentResult) -> ExecutionResult:
        text = intent.data.get("text") or intent.target
        if not text:
            return ExecutionResult(False, "No text to find on page.")
        self._hotkey(["ctrl", "f"])
        time.sleep(0.05)
        pyperclip.copy(text)
        self._hotkey(["ctrl", "v"])
        return ExecutionResult(True, f"Finding '{text}' on page.")

    def _open_known_folder(self, op: str) -> ExecutionResult:
        folder_map = {
            "open_desktop": Path.home() / "Desktop",
            "open_downloads": Path.home() / "Downloads",
            "open_documents": Path.home() / "Documents",
            "open_pictures": Path.home() / "Pictures",
            "open_videos": Path.home() / "Videos",
            "open_music": Path.home() / "Music",
        }
        path = folder_map.get(op)
        if path:
            try:
                if IS_WINDOWS:
                    os.startfile(str(path))
                elif IS_MAC:
                    subprocess.Popen(["open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif IS_LINUX:
                    subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return ExecutionResult(True, f"Opened {path.name}.", observed_state={"path": str(path)})
            except Exception as e:
                return ExecutionResult(False, f"Failed to open {path.name}: {e}")

        # Special shell folders (Windows)
        if op == "open_recent" and IS_WINDOWS:
            os.startfile("shell:recent")
            return ExecutionResult(True, "Opened Recent files.")
        if op == "open_recent" and IS_MAC:
            recent = Path.home() / "Library" / "Recent"
            if recent.exists():
                subprocess.Popen(["open", str(recent)])
                return ExecutionResult(True, "Opened Recent files.")

        return ExecutionResult(False, f"Unknown folder: {op}")

    def _open_settings(self, intent: IntentResult) -> ExecutionResult:
        page = (intent.data.get("page") or "").strip().lower()
        url = f"ms-settings:{page}" if page else "ms-settings:"
        os.startfile(url)
        return ExecutionResult(True, f"Opened Settings{f' ({page})' if page else ''}.")

    def _switch_to_window(self, target: str) -> ExecutionResult:
        """Bring a named window to the foreground."""
        import subprocess
        target_lower = target.strip().lower()
        if not target_lower:
            return self._hotkey(["alt", "tab"], "Switched window.")

        if IS_WINDOWS:
            try:
                ps_cmd = (
                    "$p = Get-Process | Where-Object { $_.MainWindowTitle -like '*" + target_lower + "*' } | "
                    "Select-Object -First 1; "
                    "if ($p) { "
                    "  Add-Type -AssemblyName Microsoft.VisualBasic; "
                    "  [Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) | Out-Null; "
                    "  Write-Output $p.MainWindowTitle "
                    "}"
                )
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=5,
                )
                if result.stdout.strip():
                    return ExecutionResult(True, f"Switched to {result.stdout.strip()}.")
            except Exception:
                pass

        return self._hotkey(["alt", "tab"], f"Switched window.")

    def _adjust_brightness(self, delta: int) -> ExecutionResult:
        """Adjust screen brightness by delta using native WMI on Windows."""
        if IS_WINDOWS:
            try:
                ps_cmd = (
                    "$mon = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness; "
                    "$current = $mon.CurrentBrightness; "
                    "$new = [Math]::Min(100, [Math]::Max(0, $current + {delta})); "
                    "(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $new) | Out-Null; "
                    "Write-Output $new"
                ).format(delta=delta)
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    return ExecutionResult(True, f"Brightness adjusted by {delta}.")
            except Exception as e:
                logger.warning(f"Native brightness failed: {e}")

        # Fallback: open Settings
        return self._open_settings(IntentResult("pc_action", "pc", "", {"page": "display"}, 1.0, "")).as_tuple()

    def _type_text(self, intent: IntentResult) -> ExecutionResult:
        text = intent.data.get("text") or intent.target
        if not text:
            return ExecutionResult(False, "No text to type.")
        self._type_text_direct(text)
        return ExecutionResult(True, f"Typed: {text[:60]}")

    def _press(self, key: str) -> ExecutionResult:
        if not key:
            return ExecutionResult(False, "No key specified.")
        media_map = {
            "media_play_pause": platform_play,
            "media_next": platform_next,
            "media_previous": platform_prev,
            "volume_up": platform_vol_up,
            "volume_down": platform_vol_down,
            "volume_mute": platform_mute,
        }
        handler = media_map.get(key)
        if handler:
            handler()
            return ExecutionResult(True, f"Pressed {key}.")
        self._tap_keys([key])
        return ExecutionResult(True, f"Pressed {key}.")

    def _hotkey(self, keys: Iterable[str], message: str = "Pressed hotkey.") -> ExecutionResult:
        keys = list(keys)
        if not keys:
            return ExecutionResult(False, "No hotkey specified.")
        self._tap_keys(keys)
        return ExecutionResult(True, message)

    def _tap_keys(self, keys: Iterable[str]):
        platform_keys(list(keys))

    def _get_battery_status(self) -> ExecutionResult:
        pct = platform_battery()
        if pct >= 0:
            return ExecutionResult(True, f"Battery is at {pct}%.", observed_state={"battery": pct})
        return ExecutionResult(False, "Could not retrieve battery info.")

    def _get_current_time(self) -> ExecutionResult:
        now = time.strftime("%I:%M %p")
        return ExecutionResult(True, f"The current time is {now}.", observed_state={"time": now})

    def _get_current_date(self) -> ExecutionResult:
        today = time.strftime("%A, %B %d, %Y")
        return ExecutionResult(True, f"Today is {today}.", observed_state={"date": today})

    def _get_system_health(self) -> ExecutionResult:
        cpu = platform_cpu()
        return ExecutionResult(True, f"System Health: CPU usage is at {cpu:.1f}%.", observed_state={"cpu_usage": cpu})

    def _get_current_user(self) -> ExecutionResult:
        user = os.getenv("USERNAME") or os.getenv("USER") or "Unknown"
        return ExecutionResult(True, f"Current user is {user}.", observed_state={"user": user})

    def _get_ip_address(self) -> ExecutionResult:
        import subprocess
        try:
            if IS_WINDOWS:
                result = subprocess.run(["powershell", "-NoProfile", "-Command",
                    "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -ne 'Loopback'}).IPAddress"],
                    capture_output=True, text=True, timeout=10)
                ips = [ip.strip() for ip in result.stdout.strip().splitlines() if ip.strip()]
                if ips:
                    return ExecutionResult(True, f"IP address: {ips[0]}", observed_state={"ip": ips[0]})
            elif IS_MAC:
                result = subprocess.run(["ipconfig", "getifaddr", "en0"], capture_output=True, text=True, timeout=5)
                if result.stdout.strip():
                    return ExecutionResult(True, f"IP address: {result.stdout.strip()}")
            elif IS_LINUX:
                result = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5)
                ip = result.stdout.strip().split()[0] if result.stdout.strip() else ""
                if ip:
                    return ExecutionResult(True, f"IP address: {ip}")
        except Exception as e:
            logger.warning(f"IP lookup failed: {e}")
        return ExecutionResult(False, "Could not determine IP address.")

    def _get_screen_resolution(self) -> ExecutionResult:
        try:
            import pyautogui
            w, h = pyautogui.size()
            return ExecutionResult(True, f"Screen resolution is {w}x{h}.", observed_state={"width": w, "height": h})
        except ImportError:
            pass
        if IS_WINDOWS:
            try:
                import ctypes
                user32 = ctypes.windll.user32
                w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
                return ExecutionResult(True, f"Screen resolution is {w}x{h}.")
            except Exception:
                pass
        return ExecutionResult(False, "Could not determine screen resolution.")

    def _empty_recycle_bin(self) -> ExecutionResult:
        if IS_WINDOWS:
            try:
                import subprocess
                ps_cmd = "(New-Object -ComObject Shell.Application).Namespace(0xa).Items() | ForEach-Object { $_.InvokeVerb('delete') }"
                subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, timeout=30)
                return ExecutionResult(True, "Emptied recycle bin.")
            except Exception as e:
                return ExecutionResult(False, f"Failed to empty recycle bin: {e}")
        return ExecutionResult(False, "Recycle bin only available on Windows.")

    def _break_timer(self) -> ExecutionResult:
        import threading
        def _remind():
            time.sleep(300)
            from core.tts_engine import get_tts_engine
            get_tts_engine().say("Break time! Take a moment to rest your eyes.")
        threading.Thread(target=_remind, daemon=True).start()
        return ExecutionResult(True, "I'll remind you to take a break in 5 minutes.")

    def _toggle_night_light(self) -> ExecutionResult:
        if IS_WINDOWS:
            os.startfile("ms-settings:nightlight")
            return ExecutionResult(True, "Opened night light settings.")
        return ExecutionResult(False, "Night light only available on Windows.")

    def _toggle_focus_assist(self) -> ExecutionResult:
        if IS_WINDOWS:
            os.startfile("ms-settings:quietmomentshome")
            return ExecutionResult(True, "Opened focus assist settings.")
        return ExecutionResult(False, "Focus assist only available on Windows.")

    def _screenshot(self) -> ExecutionResult:
        out_dir = Path("data/screenshots")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"screenshot_{int(time.time())}.png"
        if platform_screenshot(str(out_path.resolve())):
            return ExecutionResult(True, f"Saved screenshot to {out_path}.", observed_state={"path": str(out_path)})
        return ExecutionResult(False, "Screenshot failed.")

    def _resolve_path(self, target: str) -> Path | None:
        if not target:
            return None
        expanded = Path(os.path.expandvars(os.path.expanduser(target.strip('"'))))
        if expanded.exists():
            return expanded
        matches = self._find_matches(target)
        return matches[0] if matches else None

    def _find_matches(self, query: str) -> list[Path]:
        query = query.strip().strip('"').lower()
        if not query: return []
        
        results: list[Path] = []
        # Priority 1: Direct check in SAFE_DIRS (Very Fast)
        for root in SAFE_DIRS:
            if not root.exists(): continue
            try:
                for entry in os.scandir(root):
                    if query in entry.name.lower():
                        results.append(Path(entry.path))
                    if len(results) >= 10: return results
            except Exception: continue

        # Priority 2: One level deep search (Fast)
        for root in SAFE_DIRS:
            if not root.exists(): continue
            try:
                for entry in os.scandir(root):
                    if entry.is_dir():
                        for sub in os.scandir(entry.path):
                            if query in sub.name.lower():
                                results.append(Path(sub.path))
                            if len(results) >= 15: return results
            except Exception: continue

        # Priority 3: Deep search fallback (Limited)
        if not results:
            for root in SAFE_DIRS:
                if not root.exists(): continue
                try:
                    for p in root.rglob(f"*{query}*"):
                        results.append(p)
                        if len(results) >= 5: break
                except: continue
                
        return results
