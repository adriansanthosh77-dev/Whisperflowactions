"""
tools_browser.py — Browser automation MCP tools.

Site speed-dial, search, and general browser automation exposed as MCP tools.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SITES = {
    "youtube": "https://youtube.com",
    "google": "https://google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "reddit": "https://reddit.com",
    "twitter": "https://x.com",
    "facebook": "https://facebook.com",
    "instagram": "https://instagram.com",
    "linkedin": "https://linkedin.com",
    "amazon": "https://amazon.com",
    "netflix": "https://netflix.com",
    "spotify": "https://open.spotify.com",
    "notion": "https://notion.so",
    "chatgpt": "https://chatgpt.com",
    "claude": "https://claude.ai",
    "perplexity": "https://perplexity.ai",
    "gemini": "https://gemini.google.com",
    "stackoverflow": "https://stackoverflow.com",
    "wikipedia": "https://wikipedia.org",
    "maps": "https://maps.google.com",
    "outlook": "https://outlook.com",
    "discord": "https://discord.com/app",
    "slack": "https://slack.com",
    "figma": "https://figma.com",
    "jira": "https://jira.com",
    "trello": "https://trello.com",
    "translate": "https://translate.google.com",
}


def register_browser_tools(mcp):
    B = _browser_facade()

    for site_name, url in SITES.items():
        site_doc = site_name.replace("_", " ").title()

        @mcp.tool(name=f"browser_open_{site_name}")
        def _make_open(site=site_name, url=url, doc=site_doc):
            """Open {doc} in the browser. Use when user says 'open {site}'."""
            return f"Open {site}: " + B.open_url(url)
        _make_open.__name__ = f"browser_open_{site_name}"
        _make_open.__doc__ = _make_open.__doc__.replace("{site}", site_name).replace("{doc}", site_doc)

    @mcp.tool(name="browser_search")
    def browser_search(query: str, site: Optional[str] = None) -> str:
        """Search the web. Optionally specify a site (google, youtube, amazon, etc.).
        Args:
            query: The search query
            site: Optional site to search on (e.g. 'google', 'youtube', 'amazon')
        """
        if site and site.lower() in SITES:
            return B.search_site(query, site.lower())
        return B.search_google(query)

    @mcp.tool(name="browser_navigate")
    def browser_navigate(url: str) -> str:
        """Navigate to a specific URL in the browser.
        Args:
            url: The full URL to navigate to
        """
        return B.open_url(url)

    @mcp.tool(name="browser_click")
    def browser_click(selector_or_text: str) -> str:
        """Click an element on the current page by its text or CSS selector.
        Args:
            selector_or_text: Text of the element to click, or CSS selector
        """
        return "browser_click: " + selector_or_text

    @mcp.tool(name="browser_extract")
    def browser_extract(selector_or_question: str) -> str:
        """Extract text content from the current page.
        Args:
            selector_or_question: CSS selector to extract, or a question about the page content
        """
        return "browser_extract: " + selector_or_question

    @mcp.tool(name="browser_scroll")
    def browser_scroll(direction: str = "down", amount: str = "window") -> str:
        """Scroll the current page.
        Args:
            direction: 'up', 'down', 'top', or 'bottom'
            amount: 'window' for one viewport, 'half' for half viewport
        """
        return f"browser_scroll: {direction} {amount}"

    logger.info(f"Registered browser tools")


SEARCH_TEMPLATES = {
    "google": "https://google.com/search?q={q}",
    "youtube": "https://youtube.com/results?search_query={q}",
    "amazon": "https://amazon.com/s?k={q}",
    "reddit": "https://reddit.com/search?q={q}",
    "twitter": "https://x.com/search?q={q}",
    "github": "https://github.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
    "wikipedia": "https://en.wikipedia.org/wiki/{q}",
}


class _browser_facade:
    def open_url(self, url: str) -> str:
        try:
            from executors.browser_executor import BrowserExecutor
            be = BrowserExecutor()
            be.open_url(url)
            return "OK"
        except Exception as e:
            return f"Error: {e}"

    def search_google(self, query: str) -> str:
        return self.open_url(f"https://google.com/search?q={query.replace(' ', '+')}")

    def search_site(self, query: str, site: str) -> str:
        tmpl = SEARCH_TEMPLATES.get(site)
        if tmpl:
            return self.open_url(tmpl.format(q=query.replace(' ', '+')))
        site_url = SITES.get(site)
        if site_url:
            return self.open_url(site_url)
        return self.search_google(query)
