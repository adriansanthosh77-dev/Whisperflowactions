"""
tools_composio.py — Composio app integration tools for MCP.

Composio (composio.dev) connects LLMs to 200+ apps (Gmail, Slack, Notion, GitHub, etc.)
Needs COMPOSIO_API_KEY in .env to function.
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY", "")


def register_composio_tools(mcp):
    if not COMPOSIO_API_KEY:
        logger.warning("No COMPOSIO_API_KEY set — Composio tools disabled")

        @mcp.tool(name="composio_execute")
        def composio_execute(app: str, action: str, params: str = "{}") -> str:
            """Execute an action on an external app using Composio.
            NOTE: COMPOSIO_API_KEY not configured. Set in .env to enable.
            Args:
                app: App name (e.g. 'gmail', 'slack', 'github', 'notion', 'jira')
                action: Action name (e.g. 'send_email', 'create_issue', 'list_messages')
                params: JSON string of action parameters
            """
            return "Composio is not configured. Set COMPOSIO_API_KEY in .env to enable."

        @mcp.tool(name="composio_list_apps")
        def composio_list_apps() -> str:
            """List all available Composio app integrations."""
            return "Composio is not configured. Set COMPOSIO_API_KEY in .env to enable."
        return

    @mcp.tool(name="composio_execute")
    def composio_execute(app: str, action: str, params: str = "{}") -> str:
        """Execute an action on an external app using Composio.
        Supports 200+ apps including: gmail, slack, github, notion, jira, asana, linear, etc.
        Args:
            app: App name (e.g. 'gmail', 'slack', 'github', 'notion', 'jira')
            action: Action name (e.g. 'send_email', 'create_issue', 'list_messages')
            params: JSON string of action parameters
        """
        try:
            from composio.client import Composio
            client = Composio(api_key=COMPOSIO_API_KEY)
            result = client.execute_action(
                app_name=app,
                action_name=action,
                params=json.loads(params),
            )
            return json.dumps(result, indent=2)
        except ImportError:
            return "Composio SDK not installed. Run: pip install composio-core"
        except Exception as e:
            return f"Composio error: {e}"

    @mcp.tool(name="composio_list_apps")
    def composio_list_apps() -> str:
        """List all available Composio app integrations that are connected."""
        try:
            from composio.client import Composio
            client = Composio(api_key=COMPOSIO_API_KEY)
            apps = client.apps.list()
            return "\n".join(sorted(a.name for a in apps))
        except Exception as e:
            return f"Composio error: {e}"
