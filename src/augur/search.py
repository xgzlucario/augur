"""Web search abstraction. Provider factory selects based on env config.

Supported providers:
  - Exa     (EXA_API_KEY)
  - Tavily  (TAVILY_API_KEY)

Precedence when multiple keys are set: Exa wins by default. To force Tavily
(or pin Exa explicitly), set `SEARCH_PROVIDER=exa|tavily`.

Adding another provider (Serper, Brave, ...):
  1. Implement a class with `async def search(self, query, num_results) -> list[SearchResult]`
  2. Extend `get_provider()` to return it when the relevant env var is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    published_date: str | None = None

    def format_for_prompt(self) -> str:
        date = f" ({self.published_date})" if self.published_date else ""
        return f"- [{self.title}]{date}\n  {self.url}\n  {self.snippet}"


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        ...


class ExaSearch:
    """Exa web search provider. https://docs.exa.ai/reference/search"""

    name = "exa"

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        payload = {
            "query": query,
            "numResults": num_results,
            "type": "auto",
            "contents": {
                # Exa returns text excerpts with the hit so we don't need a separate fetch
                "text": {"maxCharacters": 4000},
                "highlights": {"numSentences": 3, "highlightsPerUrl": 1},
            },
        }
        headers = {
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    "https://api.exa.ai/search",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning(f"exa search failed for query {query!r}: {type(e).__name__}: {e}")
            return []

        out: list[SearchResult] = []
        for item in data.get("results", []):
            # Prefer highlights over raw text — they're pre-trimmed to relevance
            highlights = item.get("highlights") or []
            snippet = " ... ".join(highlights) if highlights else (item.get("text") or "")[:4000]
            out.append(
                SearchResult(
                    title=item.get("title") or "(untitled)",
                    url=item.get("url", ""),
                    snippet=snippet.strip(),
                    published_date=item.get("publishedDate"),
                )
            )
        return out


class TavilySearch:
    """Tavily web search provider. https://docs.tavily.com/docs/rest-api/api-reference"""

    name = "tavily"

    def __init__(self, api_key: str, timeout: float = 30.0, advanced: bool = False) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._search_depth = "advanced" if advanced else "basic"

    async def search(self, query: str, num_results: int = 10) -> list[SearchResult]:
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": num_results,
            "search_depth": self._search_depth,
            "include_answer": False,
            "include_raw_content": False,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as e:
            log.warning(f"tavily search failed for query {query!r}: {type(e).__name__}: {e}")
            return []

        out: list[SearchResult] = []
        for item in data.get("results", []):
            # Tavily returns pre-trimmed content; clamp defensively
            snippet = (item.get("content") or "").strip()[:4000]
            out.append(
                SearchResult(
                    title=item.get("title") or "(untitled)",
                    url=item.get("url", ""),
                    snippet=snippet,
                    published_date=item.get("published_date"),
                )
            )
        return out


def get_provider() -> SearchProvider | None:
    """Return a SearchProvider based on env vars, or None if none configured.

    Rules:
      - SEARCH_PROVIDER=exa|tavily forces that provider (error logged if its key is missing).
      - Otherwise the first key found wins, in order: EXA_API_KEY, TAVILY_API_KEY.
      - When both keys are set and no override is given, a one-line info is logged.
    """
    exa_key = os.environ.get("EXA_API_KEY")
    tavily_key = os.environ.get("TAVILY_API_KEY")
    override = os.environ.get("SEARCH_PROVIDER", "").strip().lower()

    if override == "exa":
        if exa_key:
            return ExaSearch(api_key=exa_key)
        log.warning("SEARCH_PROVIDER=exa but EXA_API_KEY is not set")
        return None
    if override == "tavily":
        if tavily_key:
            return TavilySearch(api_key=tavily_key)
        log.warning("SEARCH_PROVIDER=tavily but TAVILY_API_KEY is not set")
        return None
    if override:
        log.warning(f"unknown SEARCH_PROVIDER={override!r}; falling back to auto-detect")

    if exa_key:
        if tavily_key:
            log.info(
                "both EXA_API_KEY and TAVILY_API_KEY are set; using exa "
                "(set SEARCH_PROVIDER=tavily to override)"
            )
        return ExaSearch(api_key=exa_key)
    if tavily_key:
        return TavilySearch(api_key=tavily_key)
    return None


async def run_queries(
    provider: SearchProvider,
    queries: list[str],
    num_results_per_query: int = 10,
    concurrency: int = 5,
) -> dict[str, list[SearchResult]]:
    """Run multiple queries in parallel. Returns {query: results}."""
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, list[SearchResult]] = {}

    async def _one(q: str) -> None:
        async with sem:
            out[q] = await provider.search(q, num_results=num_results_per_query)

    await asyncio.gather(*(_one(q) for q in queries))
    return out
