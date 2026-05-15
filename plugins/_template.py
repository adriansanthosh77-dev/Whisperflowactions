"""
JARVIS Plugin Template.

Copy this file to create a new plugin.
Remove the underscore prefix to activate: "my_plugin.py"

Plugin API:
    REGISTER = {
        # Voice reflex triggers
        # "spoken phrase": ("operation", {extra_params})
        "reflexes": {},

        # Custom PCExecutor operations
        # "op_name": callable(intent, context) -> (bool, str)
        "operations": {},

        # MCP tool definitions
        # [{"name":..., "description":..., "handler": callable}]
        "mcp_tools": [],
    }
    def on_load(): pass   # optional — called after REGISTER is applied
    def on_unload(): pass # optional — called on reload
"""

REGISTER = {
    "reflexes": {
        "hello plugin": ("chat_reflex", {"text": "Hello from plugin!", "mode": "reply"}),
    },
    "operations": {
        "plugin_hello": lambda intent, ctx: (True, "Hello from plugin!"),
    },
    "mcp_tools": [
        {
            "name": "pc_plugin_hello",
            "description": "A plugin tool that says hello.",
            "handler": lambda: "[OK] Hello from MCP plugin!",
        },
    ],
}
