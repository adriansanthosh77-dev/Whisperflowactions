"""
plugin_manager.py — Hot-reloadable plugin system for JARVIS.

Scans plugins/ directory for .py files and merges their REGISTER dicts
into the core systems: reflexes, PC operations, and MCP tools.

Plugin API:
    REGISTER = {
        "reflexes": {"trigger phrase": ("operation", {params})},
        "operations": {"op_name": callable(intent, ctx) -> (bool, str)},
        "mcp_tools": [{"name": str, "description": str, "handler": callable}],
    }
    def on_load(): pass  # optional lifecycle hook
    def on_unload(): pass
"""
import os
import sys
import logging
import importlib.util
from pathlib import Path

logger = logging.getLogger(__name__)

PLUGIN_DIR = Path(__file__).parent.parent / "plugins"


class PluginManager:
    def __init__(self):
        self._plugins: dict[str, object] = {}
        self._reflex_extensions: list[dict] = []
        self._operation_extensions: dict[str, callable] = {}
        self._mcp_extensions: list[dict] = []

    def load_all(self):
        """Scan plugins/ directory and load every .py file."""
        if not PLUGIN_DIR.exists():
            PLUGIN_DIR.mkdir(exist_ok=True)
            logger.info("Created plugins/ directory.")
            return

        loaded = 0
        for f in sorted(PLUGIN_DIR.glob("*.py")):
            if f.name.startswith("_"):
                continue
            if self._load_one(f):
                loaded += 1

        if loaded:
            logger.info(f"Plugin system: {loaded} plugin(s) loaded, "
                        f"{len(self._reflex_extensions)} reflex groups, "
                        f"{len(self._operation_extensions)} custom ops, "
                        f"{len(self._mcp_extensions)} MCP tools")

    def _load_one(self, path: Path) -> bool:
        name = path.stem
        try:
            spec = importlib.util.spec_from_file_location(
                f"jarvis_plugin_{name}", str(path)
            )
            mod = importlib.util.module_from_spec(spec)

            # Try unloading old version if reloading
            old = self._plugins.get(name)
            if old and hasattr(old, 'on_unload'):
                try:
                    old.on_unload()
                except Exception:
                    pass

            spec.loader.exec_module(mod)

            # Standard API: REGISTER dict
            if hasattr(mod, 'REGISTER'):
                self._apply_register(name, mod.REGISTER)

            # Advanced API: on_load hook
            if hasattr(mod, 'on_load'):
                try:
                    result = mod.on_load()
                    if result is False:
                        logger.warning(f"Plugin '{name}' on_load() returned False")
                except Exception as e:
                    logger.warning(f"Plugin '{name}' on_load() raised: {e}")

            self._plugins[name] = mod
            logger.info(f"Plugin loaded: {name}")
            return True

        except SyntaxError as e:
            logger.error(f"Plugin '{name}' syntax error: {e}")
        except Exception as e:
            logger.error(f"Plugin '{name}' failed: {e}")
        return False

    def _apply_register(self, name: str, register: dict):
        reflexes = register.get("reflexes", {})
        if reflexes:
            self._reflex_extensions.append(reflexes)
            logger.info(f"  Plugin '{name}': {len(reflexes)} reflex(es)")

        ops = register.get("operations", {})
        if ops:
            self._operation_extensions.update(ops)
            logger.info(f"  Plugin '{name}': {len(ops)} operation(s)")

        tools = register.get("mcp_tools", [])
        if tools:
            self._mcp_extensions.extend(tools)
            logger.info(f"  Plugin '{name}': {len(tools)} MCP tool(s)")

    def get_reflex_keys(self) -> dict:
        """Return merged reflex dict from all plugins."""
        merged = {}
        for ext in self._reflex_extensions:
            merged.update(ext)
        return merged

    def get_operation_handler(self, op_name: str):
        """Return custom operation handler or None."""
        return self._operation_extensions.get(op_name)

    def get_mcp_tools(self):
        """Return MCP tool registrations."""
        return self._mcp_extensions

    def reload(self, name: str | None = None):
        """Reload a specific plugin or all plugins."""
        if name:
            path = PLUGIN_DIR / f"{name}.py"
            if path.exists():
                self._load_one(path)
        else:
            self.load_all()

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins."""
        return [{"name": name, "loaded": True} for name in self._plugins]


_PLUGIN_MANAGER: PluginManager | None = None


def get_plugin_manager() -> PluginManager:
    global _PLUGIN_MANAGER
    if _PLUGIN_MANAGER is None:
        _PLUGIN_MANAGER = PluginManager()
    return _PLUGIN_MANAGER
