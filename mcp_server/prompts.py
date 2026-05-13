"""
prompts.py — MCP prompt templates for JARVIS.

Reusable prompt templates that help thinking LLMs reason about
when and how to use JARVIS tools effectively.
"""


def register_prompts(mcp):
    @mcp.prompt()
    def analyze_command(user_command: str) -> str:
        """Analyze a user's command and determine the best execution strategy.
        Use this for complex commands that need step-by-step reasoning.
        """
        return f"""You are analyzing a user command to determine how JARVIS should handle it.

User command: "{user_command}"

Classify this command into ONE category:
1. **REFLEX** — Simple PC/browser automation (open app, volume, tab, click, type)
   → Execute via pc_* or browser_* tools immediately. No LLM needed.
2. **RESEARCH** — Needs web research or information gathering
   → Use exa_search or browser_search tools
3. **CODING** — Writing or modifying code
   → Use fs_read, fs_write, fs_edit, fs_run tools
4. **APP_INTEGRATION** — Needs external app (email, Slack, GitHub, Notion)
   → Use composio_execute tools (if configured) or browser automation
5. **COMPLEX** — Multi-step task needing orchestration
   → Break into subtasks, route each to the right tool

Respond with: CATEGORY and a brief reasoning."""

    @mcp.prompt()
    def task_breakdown(task: str) -> str:
        """Break down a complex task into sequential steps that JARVIS can execute.
        Each step should be one action that maps to a specific MCP tool or reflex.
        """
        return f"""Break down this task into sequential, executable steps:

Task: "{task}"

For each step, specify:
1. **Tool** — Which MCP tool or reflex to use (pc_*, browser_*, fs_*, exa_*, composio_*)
2. **Parameters** — What arguments to pass
3. **Expected result** — What the step should accomplish
4. **Fallback** — What to do if the step fails

Rules:
- Keep each step simple and atomic
- Never assume a step succeeded — check results
- Use status/context resources when you need to verify state
- If a step fails 3 times, report failure rather than retrying

Format your response as a numbered list of steps."""

    @mcp.prompt()
    def learn_from_failure(command: str, error: str) -> str:
        """Learn from a failed command so JARVIS handles similar commands better in future.
        """
        return f"""A JARVIS command failed. Analyze the failure and suggest a fix.

Command: "{command}"
Error: "{error}"

1. What went wrong? (classification mismatch? missing reflex? tool parameter error?)
2. Should a new reflex be taught for this command?
3. What would the correct tool/parameters be?
4. Should this be stored as a learned reflex for next time?"""
