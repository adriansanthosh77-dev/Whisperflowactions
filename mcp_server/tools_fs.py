"""
tools_fs.py — Filesystem tools for MCP.

Provides read/write/search capabilities for coding and file management.
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_ROOTS = [
    Path.cwd(),
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]


def _safe_path(path: str) -> Path | None:
    p = Path(path).resolve()
    for root in ALLOWED_ROOTS:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            pass
    # Also allow any path under the project
    try:
        p.relative_to(Path.cwd())
        return p
    except ValueError:
        pass
    return None


def register_fs_tools(mcp):
    @mcp.tool(name="fs_read")
    def fs_read(path: str, offset: int = 0, limit: int = 200) -> str:
        """Read a file's contents. Use for reading source code, configs, logs, etc.
        Args:
            path: Absolute or relative path to the file
            offset: Line number to start reading from (0-indexed)
            limit: Maximum number of lines to return
        """
        safe = _safe_path(path)
        if not safe:
            return f"Access denied: {path} is outside allowed directories"
        if not safe.exists():
            return f"File not found: {path}"
        try:
            lines = safe.read_text(encoding="utf-8", errors="replace").splitlines()
            selected = lines[offset:offset + limit]
            result = "\n".join(f"{i+offset+1}: {l}" for i, l in enumerate(selected))
            return result or "(empty file)"
        except Exception as e:
            return f"Error reading {path}: {e}"

    @mcp.tool(name="fs_write")
    def fs_write(path: str, content: str) -> str:
        """Write content to a file. Overwrites if exists. Use for creating/editing files.
        Args:
            path: Absolute or relative path to the file
            content: The full content to write
        """
        safe = _safe_path(path)
        if not safe:
            return f"Access denied: {path} is outside allowed directories"
        try:
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return f"Written {len(content)} bytes to {safe}"
        except Exception as e:
            return f"Error writing {path}: {e}"

    @mcp.tool(name="fs_edit")
    def fs_edit(path: str, old_string: str, new_string: str) -> str:
        """Edit a file by replacing text. Use for surgical code changes.
        Args:
            path: Absolute or relative path to the file
            old_string: The exact text to find and replace
            new_string: The replacement text
        """
        safe = _safe_path(path)
        if not safe:
            return f"Access denied: {path} is outside allowed directories"
        if not safe.exists():
            return f"File not found: {path}"
        try:
            text = safe.read_text(encoding="utf-8")
            if old_string not in text:
                return f"old_string not found in {path}"
            count = text.count(old_string)
            text = text.replace(old_string, new_string, 1)
            safe.write_text(text, encoding="utf-8")
            return f"Replaced 1 occurrence in {path} ({count} total matches)"
        except Exception as e:
            return f"Error editing {path}: {e}"

    @mcp.tool(name="fs_list")
    def fs_list(path: str = ".") -> str:
        """List files and directories in a given path.
        Args:
            path: Directory path to list (default: current directory)
        """
        safe = _safe_path(path)
        if not safe:
            return f"Access denied: {path} is outside allowed directories"
        if not safe.exists():
            return f"Directory not found: {path}"
        try:
            entries = sorted(safe.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = []
            for e in entries:
                suffix = "/" if e.is_dir() else ""
                lines.append(f"{e.name}{suffix}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listing {path}: {e}"

    @mcp.tool(name="fs_search")
    def fs_search(pattern: str, path: str = ".", include: str = "*.py") -> str:
        """Search for a pattern in files. Use for finding code, grep-style.
        Args:
            pattern: Regex pattern to search for
            path: Directory to search in (default: current)
            include: File glob pattern (e.g. '*.py', '*.{ts,tsx}')
        """
        safe = _safe_path(path) if path != "." else Path.cwd()
        if not safe:
            return f"Access denied: {path}"
        try:
            import re
            matches = []
            for f in safe.rglob(include):
                if f.is_file():
                    try:
                        for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                            if re.search(pattern, line):
                                matches.append(f"{f.relative_to(safe)}:{i}: {line.strip()[:120]}")
                    except Exception:
                        pass
            if not matches:
                return f"No matches for {pattern!r} in {safe}"
            return "\n".join(matches[:50])
        except Exception as e:
            return f"Error searching: {e}"

    @mcp.tool(name="fs_run")
    def fs_run(command: str, workdir: str = ".") -> str:
        """Run a shell command and return the output. Use for testing code, running builds, etc.
        Args:
            command: The shell command to run
            workdir: Working directory for the command
        """
        import subprocess
        safe_dir = _safe_path(workdir) if workdir != "." else Path.cwd()
        if not safe_dir:
            return f"Access denied: {workdir}"
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=str(safe_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = result.stdout or ""
            err = result.stderr or ""
            if err:
                out += f"\n[stderr]\n{err}"
            return out[:5000] or "(no output)"
        except subprocess.TimeoutExpired:
            return "Command timed out after 30s"
        except Exception as e:
            return f"Error running command: {e}"
