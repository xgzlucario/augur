"""Phase 1: build a market snapshot grounded in live web search.

The research half is delegated to `research_agent.run_research_agent`, which
drives a search/finish tool loop. The synthesis half (structured Snapshot from
raw results) stays here.
"""

import logging
from datetime import date
from typing import Callable

from openai import AsyncOpenAI

from augur.client import get_model_synthesis, language_instruction
from augur.json_utils import extract_json
from augur.research_agent import (
    QueryPlanningError,
    SearchFailedError,
    run_research_agent,
)
from augur.schemas import Snapshot
from augur.search import SearchProvider, SearchResult

log = logging.getLogger(__name__)

# Re-exports: cli.py imports these error types from snapshot. Keep the seam
# stable so external callers don't need to learn the new module.
__all__ = ["QueryPlanningError", "SearchFailedError", "SnapshotResult", "build_snapshot"]


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


class SnapshotResult:
    """Tuple-ish return for build_snapshot. Dataclass would work too; we keep
    it light because only the pipeline reads it."""

    __slots__ = ("snapshot", "steps_used", "usage")

    def __init__(self, snapshot: Snapshot, steps_used: int, usage: dict) -> None:
        self.snapshot = snapshot
        self.steps_used = steps_used
        self.usage = usage


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
    usage: dict,
    lang: str = "en",
) -> Snapshot:
    search_text = _format_search_results(results)
    response = await client.chat.completions.create(
        model=get_model_synthesis(),
        messages=[
            {
                "role": "system",
                "content": SNAPSHOT_FROM_SEARCH_SYSTEM + language_instruction(lang),
            },
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
    if response.usage is not None:
        usage["prompt_tokens"] += response.usage.prompt_tokens
        usage["completion_tokens"] += response.usage.completion_tokens
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError(f"snapshot synthesis returned empty content for {ticker}")
    snapshot = Snapshot.model_validate(extract_json(content))
    snapshot.ticker = ticker
    snapshot.as_of = as_of
    return snapshot


async def build_snapshot(
    client: AsyncOpenAI,
    ticker: str,
    search_provider: SearchProvider,
    max_steps: int = 10,
    on_step: Callable[[int, str, int, int], None] | None = None,
    on_finish: Callable[[str, int], None] | None = None,
    lang: str = "en",
) -> SnapshotResult:
    """Phase 1 entry point: agentic research loop + synthesis.

    Callbacks (optional):
      on_step(step, query, n_new, n_total_unique) — fired after each search.
      on_finish(reason, n_total_unique) — fired once the agent calls finish.

    Raises:
      QueryPlanningError — agent could not drive a usable trajectory.
      SearchFailedError — agent finished with zero unique results.
    """
    as_of = date.today().isoformat()
    log.info(f"starting research agent for {ticker} via {search_provider.name}")

    agent_result = await run_research_agent(
        client,
        ticker=ticker,
        as_of=as_of,
        provider=search_provider,
        max_steps=max_steps,
        on_step=on_step,
        on_finish=on_finish,
        lang=lang,
    )

    log.info(
        f"agent finished: {agent_result.steps_used} steps, "
        f"{sum(len(v) for v in agent_result.results_by_query.values())} total hits, "
        f"{len(agent_result.results_by_query)} unique queries"
    )

    usage = dict(agent_result.usage)
    snapshot = await _synthesize_from_search(
        client, ticker, as_of, agent_result.results_by_query, usage, lang=lang
    )
    return SnapshotResult(snapshot=snapshot, steps_used=agent_result.steps_used, usage=usage)
