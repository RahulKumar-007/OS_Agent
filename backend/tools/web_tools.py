"""
Web / Browser Integration Tools.
Web search and page scraping — the agent's window to the outside world.
Requires internet access; degrades gracefully (clear error) when offline
or dependencies are missing, keeping the rest of the agent fully offline-first.
"""

import re
from typing import Dict
from urllib.parse import parse_qs, urlparse

import httpx

from tools.base import Tool, ToolResult

try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 AEGIS-Agent/1.0"
)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for information (requires internet access). Returns "
        "titles, URLs, and text snippets — useful for research, fact-checking, "
        "or finding documentation the agent doesn't have locally."
    )
    parameters_schema = {
        "query": "Search query",
        "max_results": "(optional) Max results to return. Default 5.",
    }

    @staticmethod
    def _resolve_url(href: str) -> str:
        """Unwrap DuckDuckGo's '//duckduckgo.com/l/?uddg=<real_url>' redirect links."""
        if not href:
            return href
        if href.startswith("//"):
            href = "https:" + href
        parsed = urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            qs = parse_qs(parsed.query)
            real = qs.get("uddg", [None])[0]
            if real:
                return real
        return href

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_BS4:
            return ToolResult(
                success=False,
                message="beautifulsoup4 not installed. Run: pip install beautifulsoup4",
            )
        query = args.get("query", "").strip()
        max_results = int(args.get("max_results", 5))
        if not query:
            return ToolResult(success=False, message="Query required")

        try:
            async with httpx.AsyncClient(
                timeout=10, headers={"User-Agent": USER_AGENT}
            ) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/", params={"q": query}
                )
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            results = []
            for result in soup.select(".result")[: max_results * 2]:
                title_el = result.select_one(".result__a")
                snippet_el = result.select_one(".result__snippet")
                if not title_el:
                    continue
                url = self._resolve_url(title_el.get("href", ""))
                results.append(
                    {
                        "title": title_el.get_text(strip=True),
                        "url": url,
                        "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                    }
                )
                if len(results) >= max_results:
                    break

            return ToolResult(
                success=True,
                data={"query": query, "results": results, "count": len(results)},
                message=f"Found {len(results)} result(s) for '{query}'",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, message=f"Network error — internet connection required: {e}"
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Web search failed: {e}")


class WebScrapeTool(Tool):
    name = "web_scrape"
    description = (
        "Fetch a web page and extract its readable text content, title, and links "
        "(requires internet access). Use after web_search to pull full content from "
        "a promising result."
    )
    parameters_schema = {
        "url": "Full URL to fetch (http:// or https://)",
        "max_length": "(optional) Max characters of text to return. Default 5000.",
    }

    async def execute(self, args: Dict) -> ToolResult:
        if not HAS_BS4:
            return ToolResult(
                success=False,
                message="beautifulsoup4 not installed. Run: pip install beautifulsoup4",
            )
        url = args.get("url", "").strip()
        max_length = int(args.get("max_length", 5000))
        if not url:
            return ToolResult(success=False, message="URL required")
        if not re.match(r"^https?://", url):
            url = "https://" + url

        try:
            async with httpx.AsyncClient(
                timeout=15, headers={"User-Agent": USER_AGENT}, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()

            title = soup.title.get_text(strip=True) if soup.title else ""
            text = re.sub(
                r"\n{3,}", "\n\n", soup.get_text(separator="\n", strip=True)
            )
            truncated = text[:max_length]

            links = []
            for a in soup.find_all("a", href=True)[:50]:
                href = a["href"]
                if href.startswith("http"):
                    links.append({"text": a.get_text(strip=True)[:80], "url": href})

            return ToolResult(
                success=True,
                data={
                    "url": url,
                    "title": title,
                    "text": truncated,
                    "truncated": len(text) > max_length,
                    "links": links,
                },
                message=f"Scraped '{title or url}' ({len(truncated)} chars)",
            )
        except httpx.RequestError as e:
            return ToolResult(
                success=False, message=f"Network error — internet connection required: {e}"
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Scrape failed: {e}")


ALL_WEB_TOOLS = [WebSearchTool(), WebScrapeTool()]
