import json
import logging
from datetime import date

from openai import AsyncOpenAI

from augur.client import get_model_synthesis
from augur.json_utils import extract_json
from augur.schemas import Snapshot
from augur.search import SearchProvider, SearchResult, run_queries

log = logging.getLogger(__name__)

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
    )

    content = response.choices[0].message.content or ""
    try:
        data = extract_json(content)
        queries = data.get("queries") or []
    except (json.JSONDecodeError, AttributeError) as e:
        log.warning(
            f"query planner returned unparsable output ({type(e).__name__}); "
            f"falling back to defaults. First 200 chars: {content[:200]!r}"
        )
        queries = []

    if not queries:
        queries = [
            f"{ticker} latest earnings results",
            f"{ticker} stock price analysis recent",
            f"{ticker} analyst ratings price target",
            f"{ticker} competitive landscape risks",
        ]
    return [str(q) for q in queries if q]


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

# ---------- Prompt 2 (fallback): LLM-only snapshot, no search ----------

SNAPSHOT_LLM_ONLY_SYSTEM = """You are a senior equity research analyst.

Produce a concise, factual snapshot of a ticker from your training knowledge.
The snapshot must be balanced and multi-faceted — cover bull and bear angles,
value and growth data, macro and company-specific.

You do NOT have internet access. If you are unsure about recent events or
numbers, say so explicitly in the relevant field rather than fabricating.
Flag staleness where it matters.

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
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"snapshot synthesis returned empty content for {ticker}")
    snapshot = Snapshot.model_validate(extract_json(content))
    snapshot.ticker = ticker
    snapshot.as_of = as_of
    return snapshot


async def _snapshot_llm_only(client: AsyncOpenAI, ticker: str, as_of: str) -> Snapshot:
    response = await client.chat.completions.create(
        model=get_model_synthesis(),
        messages=[
            {"role": "system", "content": SNAPSHOT_LLM_ONLY_SYSTEM},
            {
                "role": "user",
                "content": f"Build a market snapshot for ticker {ticker}, dated {as_of}.",
            },
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"snapshot returned empty content for {ticker}")
    snapshot = Snapshot.model_validate(extract_json(content))
    snapshot.ticker = ticker
    snapshot.as_of = as_of
    return snapshot


# ---------- Public entry point ----------


async def build_snapshot(
    client: AsyncOpenAI,
    ticker: str,
    search_provider: SearchProvider | None = None,
) -> Snapshot:
    """Phase 1: produce a market snapshot.

    If `search_provider` is given, plan queries → execute search → synthesize
    snapshot from results. Otherwise fall back to LLM-only (training knowledge).
    """
    as_of = date.today().isoformat()

    if search_provider is None:
        log.info("no search provider configured; using LLM-only snapshot")
        return await _snapshot_llm_only(client, ticker, as_of)

    log.info(f"planning search queries for {ticker} via {search_provider.name}")
    queries = await _plan_queries(client, ticker, as_of)
    log.info(f"running {len(queries)} queries: {queries}")

    results = await run_queries(search_provider, queries, num_results_per_query=5)
    total_hits = sum(len(v) for v in results.values())
    log.info(f"collected {total_hits} results across {len(queries)} queries")

    if total_hits == 0:
        log.warning("search returned zero results; falling back to LLM-only")
        return await _snapshot_llm_only(client, ticker, as_of)

    return await _synthesize_from_search(client, ticker, as_of, results)
