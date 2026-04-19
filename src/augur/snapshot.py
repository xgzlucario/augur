import json
import logging
from datetime import date
from typing import Callable

from openai import AsyncOpenAI

from augur.client import get_model_synthesis
from augur.json_utils import extract_json
from augur.schemas import Snapshot
from augur.search import SearchProvider, SearchResult, run_queries

log = logging.getLogger(__name__)


class QueryPlanningError(RuntimeError):
    """Raised when the LLM fails to produce a valid search-query plan."""


class SearchFailedError(RuntimeError):
    """Raised when the search provider returns no usable results."""


# ---------- Prompt 1: query planner ----------

PLANNER_SYSTEM = """You are a research analyst planning a web search for a ticker.

Given a ticker, produce 4-6 diverse search queries that together build a
multi-faceted picture: fundamentals, recent earnings, analyst sentiment,
competitive landscape, and macro/sector context. The queries will be executed
verbatim against a web search engine, so phrase them as someone would type them.

OUTPUT RULES (critical):
- Respond with a single JSON object and NOTHING else.
- No markdown fences, no ```json blocks, no prose before or after.
- The object must have exactly one key "queries" whose value is a string array.

Example of the ONLY acceptable output format:
{"queries": ["AAPL Q4 2025 earnings", "AAPL analyst price target 2026", "AAPL iPhone China sales", "AAPL services revenue growth"]}
"""


async def _plan_queries(client: AsyncOpenAI, ticker: str, as_of: str) -> list[str]:
    response = await client.chat.completions.create(
        model=get_model_synthesis(),
        messages=[
            {"role": "system", "content": PLANNER_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Ticker: {ticker}. Today is {as_of}. "
                    "Plan 4-6 web search queries to build a balanced market snapshot."
                ),
            },
        ],
        max_tokens=2000,
        temperature=0.1,
    )

    content = response.choices[0].message.content or ""
    try:
        data = extract_json(content)
    except json.JSONDecodeError as e:
        raise QueryPlanningError(
            f"query planner returned unparsable output: {e}. "
            f"First 300 chars of response: {content[:300]!r}"
        ) from e

    if not isinstance(data, dict):
        raise QueryPlanningError(
            f"query planner returned non-object JSON: {type(data).__name__}. "
            f"Content: {content[:300]!r}"
        )

    raw_queries = data.get("queries")
    if not isinstance(raw_queries, list) or not raw_queries:
        raise QueryPlanningError(
            f"query planner JSON missing non-empty 'queries' array. "
            f"Got: {data!r}"
        )

    queries = [str(q).strip() for q in raw_queries if str(q).strip()]
    if not queries:
        raise QueryPlanningError(
            f"query planner returned only empty queries. Got: {raw_queries!r}"
        )
    return queries


# ---------- Prompt 2: synthesize snapshot from search results ----------

SNAPSHOT_FROM_SEARCH_SYSTEM = """You are a senior equity research analyst.

You will receive a ticker and a set of web search results. Produce a balanced,
multi-faceted snapshot that a diverse panel of investors will use as shared
context. Cover bull and bear angles, value and growth data, macro and
company-specific.

Ground every claim in the search results. Do NOT fabricate numbers. If the
results don't mention something (e.g. current P/E is absent), note that the
data is unavailable rather than guessing. Attribute key facts implicitly via
concrete language ("Q3 earnings beat by X%") but don't copy URLs into the
output — those live in the raw results.

OUTPUT RULES (critical):
- Respond with a single JSON object and NOTHING else.
- No markdown fences, no ```json blocks, no prose before or after.
- Must match this schema exactly:
  {
    "ticker": string,
    "as_of": string (ISO date),
    "fundamentals": string,
    "recent_news": array of strings,
    "price_action": string,
    "sector_context": string,
    "macro_context": string
  }
"""


def _format_search_results(results: dict[str, list[SearchResult]]) -> str:
    lines = []
    for query, hits in results.items():
        lines.append(f"\n### Query: {query}")
        if not hits:
            lines.append("(no results)")
            continue
        for r in hits:
            lines.append(r.format_for_prompt())
    return "\n".join(lines)


async def _synthesize_from_search(
    client: AsyncOpenAI,
    ticker: str,
    as_of: str,
    results: dict[str, list[SearchResult]],
) -> Snapshot:
    search_text = _format_search_results(results)
    response = await client.chat.completions.create(
        model=get_model_synthesis(),
        messages=[
            {"role": "system", "content": SNAPSHOT_FROM_SEARCH_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Ticker: {ticker}\nToday: {as_of}\n\n"
                    f"=== WEB SEARCH RESULTS ===\n{search_text}\n\n"
                    "Produce the Snapshot JSON."
                ),
            },
        ],
        temperature=0.1,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"snapshot synthesis returned empty content for {ticker}")
    snapshot = Snapshot.model_validate(extract_json(content))
    snapshot.ticker = ticker
    snapshot.as_of = as_of
    return snapshot


# ---------- Public entry point ----------


async def build_snapshot(
    client: AsyncOpenAI,
    ticker: str,
    search_provider: SearchProvider,
    on_queries: Callable[[list[str]], None] | None = None,
    on_search_results: Callable[[int, int], None] | None = None,
) -> Snapshot:
    """Phase 1: produce a market snapshot grounded in live web search.

    Plan queries → execute search → synthesize snapshot from results.
    There is no LLM-only fallback: stale training knowledge is worse than
    an explicit failure.

    Callbacks (optional; never break the pipeline if they raise):
      on_queries(queries) — invoked with the planned query list before search.
      on_search_results(total_hits, n_queries) — invoked after search completes.

    Raises:
      QueryPlanningError — LLM failed to produce a valid query plan.
      SearchFailedError — search returned zero results across all queries.
    """
    as_of = date.today().isoformat()

    log.info(f"planning search queries for {ticker} via {search_provider.name}")
    queries = await _plan_queries(client, ticker, as_of)
    log.info(f"running {len(queries)} queries: {queries}")
    if on_queries is not None:
        try:
            on_queries(queries)
        except Exception:
            pass

    results = await run_queries(search_provider, queries, num_results_per_query=5)
    total_hits = sum(len(v) for v in results.values())
    log.info(f"collected {total_hits} results across {len(queries)} queries")
    if on_search_results is not None:
        try:
            on_search_results(total_hits, len(queries))
        except Exception:
            pass

    if total_hits == 0:
        raise SearchFailedError(
            f"{search_provider.name} returned zero results across all "
            f"{len(queries)} queries for {ticker}. "
            f"Check the provider's status/quota or try a different ticker."
        )

    return await _synthesize_from_search(client, ticker, as_of, results)
