"""
tools_exa.py — Exa research tools for MCP.

Exa (exa.ai) is a web search API designed for LLMs — returns clean, structured results.
Needs EXA_API_KEY in .env to function.
"""
import os
import json
import logging
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

EXA_API_KEY = os.getenv("EXA_API_KEY", "")


def register_exa_tools(mcp):
    if not EXA_API_KEY:
        logger.warning("No EXA_API_KEY set — Exa research tools disabled")

        @mcp.tool(name="exa_search")
        def exa_search(query: str, num_results: int = 5) -> str:
            """Search the web using Exa AI search engine. Provides clean, structured results for research.
            NOTE: EXA_API_KEY not configured. Set in .env to enable.
            Args:
                query: The search query
                num_results: Number of results to return (1-10)
            """
            return "Exa research is not configured. Set EXA_API_KEY in .env to enable."

        @mcp.tool(name="exa_get_contents")
        def exa_get_contents(urls: str) -> str:
            """Get the full text content of specific URLs.
            Args:
                urls: Comma-separated list of URLs to fetch
            """
            return "Exa research is not configured. Set EXA_API_KEY in .env to enable."
        return

    import httpx

    @mcp.tool(name="exa_search")
    def exa_search(query: str, num_results: int = 5) -> str:
        """Search the web using Exa AI search engine. Provides clean, structured results perfect for research.
        Use this for in-depth research, finding recent information, or getting structured web data.
        Args:
            query: The search query
            num_results: Number of results to return (1-10)
        """
        try:
            resp = httpx.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": EXA_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "query": query,
                    "numResults": min(num_results, 10),
                    "useAutoprompt": True,
                },
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return "No results found."
            lines = [f"Exa search results for: {query}", ""]
            for i, r in enumerate(results[:num_results], 1):
                title = r.get("title", "Untitled")
                url = r.get("url", "")
                snippet = r.get("text", "")[:200]
                lines.append(f"{i}. {title}")
                lines.append(f"   {url}")
                if snippet:
                    lines.append(f"   {snippet}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Exa search failed: {e}"

    @mcp.tool(name="exa_get_contents")
    def exa_get_contents(urls: str) -> str:
        """Get the full text content of specific URLs using Exa.
        Args:
            urls: Comma-separated list of URLs to fetch
        """
        try:
            url_list = [u.strip() for u in urls.split(",") if u.strip()]
            resp = httpx.post(
                "https://api.exa.ai/contents",
                headers={
                    "x-api-key": EXA_API_KEY,
                    "Content-Type": "application/json",
                },
                json={"urls": url_list, "text": True},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return "No content retrieved."
            lines = []
            for r in results:
                url = r.get("url", "")
                text = r.get("text", "")
                lines.append(f"=== {url} ===")
                lines.append(text[:2000])
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Exa contents failed: {e}"
