"""Web search abstraction. Provider factory selects based on env config.

Currently only Exa is implemented. To add another provider (Tavily, Serper, ...):
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

    async def search(self, query: str, num_results: int = 5) -> list[SearchResult]:
        payload = {
            "query": query,
            "numResults": num_results,
            "type": "auto",
            "contents": {
                # Exa returns text excerpts with the hit so we don't need a separate fetch
                "text": {"maxCharacters": 1000},
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
            snippet = " ... ".join(highlights) if highlights else (item.get("text") or "")[:500]
            out.append(
                SearchResult(
                    title=item.get("title") or "(untitled)",
                    url=item.get("url", ""),
                    snippet=snippet.strip(),
                    published_date=item.get("publishedDate"),
                )
            )
        return out


def get_provider() -> SearchProvider | None:
    """Return a SearchProvider based on env vars, or None if none configured."""
    exa_key = os.environ.get("EXA_API_KEY")
    if exa_key:
        return ExaSearch(api_key=exa_key)
    return None


async def run_queries(
    provider: SearchProvider,
    queries: list[str],
    num_results_per_query: int = 5,
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
