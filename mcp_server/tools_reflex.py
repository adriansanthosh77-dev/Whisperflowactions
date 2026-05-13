"""
tools_reflex.py — All PC reflexes as MCP tools.

Registers every reflex from the existing dictionary + regex system
as individual callable MCP tools for LLM discovery.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── PC Window Management ─────────────────────────────────────────────

def register_reflex_tools(mcp):
    PC = _pc_facade()

    # ── Window Management ──
    @mcp.tool(name="pc_window_minimize")
    def pc_window_minimize() -> str:
        """Minimize the active window. Use when user says 'minimize window', 'minimize'."""
        return PC.exec("minimize_window")

    @mcp.tool(name="pc_window_maximize")
    def pc_window_maximize() -> str:
        """Maximize the active window. Use when user says 'maximize window', 'maximize'."""
        return PC.exec("maximize_window")

    @mcp.tool(name="pc_window_close")
    def pc_window_close() -> str:
        """Close the active window or app. Use when user says 'close window', 'close app', 'exit'."""
        return PC.exec("close_window")

    @mcp.tool(name="pc_window_snap_left")
    def pc_window_snap_left() -> str:
        """Snap the active window to the left half of the screen."""
        return PC.exec("snap_left")

    @mcp.tool(name="pc_window_snap_right")
    def pc_window_snap_right() -> str:
        """Snap the active window to the right half of the screen."""
        return PC.exec("snap_right")

    @mcp.tool(name="pc_window_switch")
    def pc_window_switch(target: Optional[str] = None) -> str:
        """Switch to a different window or app. Use Alt+Tab behavior.
        Args:
            target: Optional app name to switch to (e.g. 'chrome', 'notepad')
        """
        if target:
            return PC.exec("switch_window", target=target)
        return PC.exec("press", key="alt+tab")

    @mcp.tool(name="pc_screenshot")
    def pc_screenshot() -> str:
        """Take a screenshot of the entire screen."""
        return PC.exec("screenshot")

    @mcp.tool(name="pc_show_desktop")
    def pc_show_desktop() -> str:
        """Show the desktop by minimizing all windows (Win+D)."""
        return PC.exec("show_desktop")

    @mcp.tool(name="pc_lock")
    def pc_lock() -> str:
        """Lock the PC (Win+L)."""
        return PC.exec("lock_pc")

    # ── Browser Tab Management ──
    @mcp.tool(name="pc_browser_new_tab")
    def pc_browser_new_tab() -> str:
        """Open a new browser tab (Ctrl+T). Use when user says 'new tab'."""
        return PC.exec("new_tab")

    @mcp.tool(name="pc_browser_close_tab")
    def pc_browser_close_tab() -> str:
        """Close the current browser tab (Ctrl+W). Use when user says 'close tab'."""
        return PC.exec("close_tab")

    @mcp.tool(name="pc_browser_reopen_tab")
    def pc_browser_reopen_tab() -> str:
        """Reopen the last closed tab (Ctrl+Shift+T)."""
        return PC.exec("reopen_closed_tab")

    @mcp.tool(name="pc_browser_next_tab")
    def pc_browser_next_tab() -> str:
        """Switch to the next browser tab (Ctrl+Tab)."""
        return PC.exec("next_tab")

    @mcp.tool(name="pc_browser_prev_tab")
    def pc_browser_prev_tab() -> str:
        """Switch to the previous browser tab (Ctrl+Shift+Tab)."""
        return PC.exec("prev_tab")

    @mcp.tool(name="pc_browser_reload")
    def pc_browser_reload() -> str:
        """Reload/refresh the current page (F5 or Ctrl+R)."""
        return PC.exec("reload")

    @mcp.tool(name="pc_browser_back")
    def pc_browser_back() -> str:
        """Go back to the previous page (Alt+Left)."""
        return PC.exec("browser_back")

    @mcp.tool(name="pc_browser_forward")
    def pc_browser_forward() -> str:
        """Go forward to the next page (Alt+Right)."""
        return PC.exec("browser_forward")

    @mcp.tool(name="pc_browser_focus_address")
    def pc_browser_focus_address() -> str:
        """Focus the browser address/URL bar (Ctrl+L or F6)."""
        return PC.exec("focus_address_bar")

    @mcp.tool(name="pc_browser_zoom_in")
    def pc_browser_zoom_in() -> str:
        """Zoom in on the current page (Ctrl++)."""
        return PC.exec("zoom_in")

    @mcp.tool(name="pc_browser_zoom_out")
    def pc_browser_zoom_out() -> str:
        """Zoom out on the current page (Ctrl+-)."""
        return PC.exec("zoom_out")

    @mcp.tool(name="pc_browser_zoom_reset")
    def pc_browser_zoom_reset() -> str:
        """Reset zoom to 100% (Ctrl+0)."""
        return PC.exec("zoom_reset")

    # ── Media Controls ──
    @mcp.tool(name="pc_media_play_pause")
    def pc_media_play_pause() -> str:
        """Toggle play/pause for media. Use when user says 'play', 'pause', 'play pause'."""
        return PC.exec("media_play_pause")

    @mcp.tool(name="pc_media_next")
    def pc_media_next() -> str:
        """Skip to the next track/song."""
        return PC.exec("media_next")

    @mcp.tool(name="pc_media_previous")
    def pc_media_previous() -> str:
        """Go back to the previous track/song."""
        return PC.exec("media_previous")

    @mcp.tool(name="pc_volume_up")
    def pc_volume_up() -> str:
        """Increase system volume. Use when user says 'volume up', 'louder', 'increase volume'."""
        return PC.exec("volume_up")

    @mcp.tool(name="pc_volume_down")
    def pc_volume_down() -> str:
        """Decrease system volume. Use when user says 'volume down', 'quieter'."""
        return PC.exec("volume_down")

    @mcp.tool(name="pc_volume_mute")
    def pc_volume_mute() -> str:
        """Mute or unmute system volume. Use when user says 'mute', 'unmute'."""
        return PC.exec("volume_mute")

    @mcp.tool(name="pc_fullscreen")
    def pc_fullscreen() -> str:
        """Toggle fullscreen mode (F11)."""
        return PC.exec("fullscreen")

    # ── Editing ──
    @mcp.tool(name="pc_edit_copy")
    def pc_edit_copy() -> str:
        """Copy selected text or item (Ctrl+C)."""
        return PC.exec("copy")

    @mcp.tool(name="pc_edit_paste")
    def pc_edit_paste() -> str:
        """Paste from clipboard (Ctrl+V)."""
        return PC.exec("paste")

    @mcp.tool(name="pc_edit_undo")
    def pc_edit_undo() -> str:
        """Undo the last action (Ctrl+Z)."""
        return PC.exec("undo")

    @mcp.tool(name="pc_edit_redo")
    def pc_edit_redo() -> str:
        """Redo the last undone action (Ctrl+Y)."""
        return PC.exec("redo")

    @mcp.tool(name="pc_edit_select_all")
    def pc_edit_select_all() -> str:
        """Select all content (Ctrl+A)."""
        return PC.exec("select_all")

    @mcp.tool(name="pc_edit_find")
    def pc_edit_find() -> str:
        """Open find/search dialog (Ctrl+F). Use when user says 'find', 'search on page'."""
        return PC.exec("find_on_page")

    # ── System ──
    @mcp.tool(name="pc_system_battery")
    def pc_system_battery() -> str:
        """Get the current battery level. Use when user asks about battery status."""
        return PC.exec("get_battery_status")

    @mcp.tool(name="pc_system_time")
    def pc_system_time() -> str:
        """Get the current time. Use when user asks 'what time is it'."""
        return PC.exec("get_current_time")

    @mcp.tool(name="pc_system_date")
    def pc_system_date() -> str:
        """Get today's date."""
        return PC.exec("get_current_date")

    @mcp.tool(name="pc_system_health")
    def pc_system_health() -> str:
        """Get system health info (CPU, memory usage)."""
        return PC.exec("get_system_health")

    @mcp.tool(name="pc_brightness_up")
    def pc_brightness_up() -> str:
        """Increase screen brightness."""
        return PC.exec("brightness_up")

    @mcp.tool(name="pc_brightness_down")
    def pc_brightness_down() -> str:
        """Decrease screen brightness."""
        return PC.exec("brightness_down")

    # ── Scrolling ──
    @mcp.tool(name="pc_scroll_down")
    def pc_scroll_down() -> str:
        """Scroll down the current page."""
        return PC.exec("scroll_down")

    @mcp.tool(name="pc_scroll_up")
    def pc_scroll_up() -> str:
        """Scroll up the current page."""
        return PC.exec("scroll_up")

    @mcp.tool(name="pc_scroll_to_top")
    def pc_scroll_to_top() -> str:
        """Go to the top of the current page (Ctrl+Home)."""
        return PC.exec("go_to_top")

    @mcp.tool(name="pc_scroll_to_bottom")
    def pc_scroll_to_bottom() -> str:
        """Go to the bottom of the current page (Ctrl+End)."""
        return PC.exec("go_to_bottom")

    logger.info(f"Registered {_count} reflex tools")


_count = 0
class _pc_facade:
    """Minimal facade that routes operation names to PCExecutor."""
    def exec(self, operation: str, **kwargs) -> str:
        global _count
        _count += 1
        try:
            from executors.pc_executor import PCExecutor
            from core.action_router import ActionRouter
            from core.planner import IntentResult
            _pc = PCExecutor()
            intent = IntentResult(intent="pc_action", operation=operation, extra=kwargs)
            success, msg = _pc.execute(intent, {})
            return f"[{'OK' if success else 'FAIL'}] {operation}: {msg}"
        except Exception as e:
            return f"[ERROR] {operation}: {e}"
