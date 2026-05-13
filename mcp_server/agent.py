"""
agent.py — MCP Agent for multi-step task orchestration.

Connects to the MCP server, takes a complex task, and autonomously
plans and executes it step by step using MCP tools.
"""
import os
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class MCPAgent:
    """Autonomous agent that orchestrates multi-step tasks using MCP tools."""

    def __init__(self, llm_provider: str = "ollama", llm_model: str = "llama3.2:1b"):
        self.provider = llm_provider
        self.model = llm_model
        self._mcp = None
        self._history = []

    def run(self, task: str, context: Optional[dict] = None) -> str:
        """Execute a complex task by planning and running steps autonomously."""
        try:
            plan = self._plan(task, context or {})
            if not plan:
                return "Failed to create a plan for this task."

            results = []
            for step in plan:
                step_name = step.get("tool", "unknown")
                step_params = step.get("params", {})
                logger.info(f"MCP Agent executing: {step_name}({step_params})")

                result = self._execute_step(step_name, step_params)
                results.append({"step": step_name, "result": result})

                # Check if step failed and we should stop
                if result.startswith("[ERROR]") or result.startswith("[FAIL]"):
                    if step.get("critical", True):
                        break

            return self._summarize_results(task, results)

        except Exception as e:
            logger.error(f"MCP Agent error: {e}")
            return f"MCP Agent failed: {e}"

    def _plan(self, task: str, context: dict) -> list:
        """Use LLM to create a step-by-step plan for the task."""
        prompt = f"""You are a planning agent. Given a user task, create a step-by-step plan.

Task: {task}

Context: {json.dumps(context, indent=2)}

Available tools:
- pc_* tools: Window management, browser control, media, volume, editing
- browser_* tools: Search web, open sites, navigate, click, extract
- exa_search / exa_get_contents: Web research
- fs_read / fs_write / fs_edit / fs_list / fs_search / fs_run: Filesystem operations
- composio_execute: External app integrations (Gmail, Slack, GitHub, etc.)

Return a JSON array of steps. Each step has:
  {{"tool": "tool_name", "params": {{key: value}}, "critical": true/false}}

Example:
[
  {{"tool": "browser_search", "params": {{"query": "latest AI news", "site": "google"}}, "critical": false}},
  {{"tool": "browser_extract", "params": {{"selector_or_question": "summarize the results"}}, "critical": false}}
]

Return ONLY the JSON array, no other text."""

        try:
            import httpx
            resp = httpx.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
                timeout=30,
            )
            content = resp.json().get("message", {}).get("content", "[]")
            # Extract JSON from response
            content = content.strip()
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip().strip(",")
            plan = json.loads(content)
            if isinstance(plan, list):
                return plan
            return []
        except Exception as e:
            logger.error(f"Plan creation failed: {e}")
            return []

    def _execute_step(self, tool_name: str, params: dict) -> str:
        """Execute a single MCP tool step."""
        try:
            # Map tool names to actual functions in our MCP server
            import mcp_server.server as mcp_srv
            mcp = mcp_srv.create_mcp_server()

            # FastMCP provides a tool registry via its internal graph
            tool_map = {}
            for t in mcp._tool_manager.list_tools():
                tool_map[t.name] = t.fn

            fn = tool_map.get(tool_name)
            if fn is None:
                return f"[ERROR] Tool '{tool_name}' not found"

            result = fn(**params)
            return str(result)

        except Exception as e:
            return f"[ERROR] {tool_name}: {e}"

    def _summarize_results(self, task: str, results: list) -> str:
        """Summarize the results of all steps."""
        lines = [f"Task: {task}", ""]
        success = 0
        fail = 0
        for r in results:
            status = "OK" if not (r["result"].startswith("[ERROR]") or r["result"].startswith("[FAIL]")) else "FAIL"
            if status == "OK":
                success += 1
            else:
                fail += 1
            lines.append(f"  [{status}] {r['step']}: {r['result'][:100]}")
        lines.append("")
        lines.append(f"Summary: {success} succeeded, {fail} failed")
        return "\n".join(lines)
