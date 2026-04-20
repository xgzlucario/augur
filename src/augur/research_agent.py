"""Agentic research loop for Phase 1 snapshot building.

The model drives a multi-turn loop, emitting exactly one JSON object per turn
that names a tool — `search` or `finish` — which we parse and dispatch:

  {"tool": "search", "query": "..."}   → run one web search, feed results back
  {"tool": "finish", "reason": "..."}  → stop looping; hand results to synthesis

We deliberately use JSON-in-content rather than OpenAI's native tool-calling
protocol: it works on every OpenAI-compatible endpoint (including providers
that don't speak function calling) and keeps parsing uniform with the rest of
this codebase.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from openai import AsyncOpenAI

from augur.client import get_model_synthesis, language_instruction
from augur.json_utils import extract_json
from augur.search import SearchProvider, SearchResult

log = logging.getLogger(__name__)


class QueryPlanningError(RuntimeError):
    """Raised when the research agent fails to produce a usable trajectory."""


class SearchFailedError(RuntimeError):
    """Raised when the loop finishes with zero unique results."""


SYSTEM_PROMPT_TEMPLATE = """You are an augur. In ancient Rome, the augur read
the flight of birds before the senate voted; here, you read the tape before a
council of 18 legendary investors deliberates. Your office is not to predict,
but to observe clearly — the omens speak for themselves once gathered honestly.

Today is {as_of}. Gather evidence via web search, then stop when coverage is
balanced.

## Tools

Respond on every turn with a single JSON object — one tool call, no prose,
no markdown fences:

  {{"tool": "search", "query": "<3-6 word natural phrase>"}}
  {{"tool": "finish", "reason": "<one short sentence, <= 200 chars>"}}

### Query style

Queries must read like what a human would actually type into a search engine.
Short noun phrases. Not keyword soup.

  GOOD: "AAPL Q2 2026 earnings"
  GOOD: "Fed rate decision March 2026"
  GOOD: "iPhone India production 2026"
  GOOD: "DOJ Apple antitrust ruling"
  BAD:  "Apple tariff impact China US trade war 2026 iPhone production India Vietnam"
  BAD:  "Apple Vision Pro Mac MacBook Neo sales 2026 product pipeline"
  BAD:  "Apple AI strategy 2026 Siri Apple Intelligence Google partnership Gemini"

When a stuffed query would cover 3 angles, issue 3 separate queries instead.
More focused searches beat one kitchen-sink query.

### Finish style

The reason is a log line, not a report. One sentence, <= 200 chars. Do NOT
summarize findings — the snapshot synthesis reads the raw results, not your
reason. Use the reason to say what made you stop.

  GOOD: "Coverage balanced across company, macro, policy, and supply chain; no
         more high-value angles visible."
  GOOD: "Web thin on Services segment risk; stopping before diminishing returns."
  BAD:  A multi-sentence paragraph listing Q1 revenue, EPS, partnerships, etc.

## Coverage checklist

A complete snapshot treats the company and its world with equal weight.
Before calling finish, you should have touched most of:

  Company
  - Fundamentals: revenue, margins, balance sheet
  - Latest earnings, management guidance, disclosed outlook
  - Products, customers, end-markets, competitive position
  - Insider moves, buybacks, dividends, material filings

  Backdrop (as important as fundamentals)
  - Macro regime: rates, inflation, cycle, FX, liquidity
  - Policy & regulation for the listing venue and industry
    (e.g. SEC/FDA for US, PBoC/NDRC/MIIT for A-shares, PRA/BoE for UK)
  - Geopolitics, tariffs, sanctions, export controls
  - Structural themes driving or threatening the business

Collect both bull and bear evidence across all of the above.

## Principles

- Facts over opinions. Prefer filings, earnings calls, disclosed numbers,
  price action, and dated events you can verify. AVOID sell-side analyst
  ratings and price targets — they're subjective, lagging, and rarely
  free of the issuer's business interests. The council has its own
  opinions; your job is the raw material they reason from.
- Recency: today is {as_of}. Trust the web over memory; search for the
  fiscal period an analyst would actually read today, not round-number
  years like "2024" out of habit.
- Breadth: each query opens a NEW angle. Don't repeat; don't pile on
  more company queries while backdrop is still thin.
- Honesty: never fabricate. If the web is thin on something, say so in
  the finish reason.
- Stop when balanced — more searches aren't always better.
"""


MAX_STEPS_DEFAULT = 10
RESULTS_PER_STEP = 5
SNIPPET_TRUNCATE = 1500
API_RETRIES = 3
MAX_TOKENS_PER_TURN = 1000
REASON_MAX_CHARS = 200


def _clamp_reason(raw: object) -> str:
    """Clamp finish `reason` to a single short log line.

    Strips whitespace, collapses newlines, truncates to REASON_MAX_CHARS with
    an ellipsis. The model occasionally writes a full summary here despite the
    prompt; we refuse to propagate it unchanged.
    """
    text = str(raw or "").strip().replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    if len(text) > REASON_MAX_CHARS:
        text = text[: REASON_MAX_CHARS - 1].rstrip() + "…"
    return text


@dataclass
class AgentResult:
    results_by_query: dict[str, list[SearchResult]]
    steps_used: int
    finish_reason: str
    usage: dict = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


async def run_research_agent(
    client: AsyncOpenAI,
    ticker: str,
    as_of: str,
    provider: SearchProvider,
    max_steps: int = MAX_STEPS_DEFAULT,
    on_step: Callable[[int, str, int, int], None] | None = None,
    on_finish: Callable[[str, int], None] | None = None,
    lang: str = "en",
) -> AgentResult:
    """Drive the search/finish loop and return whatever was gathered.

    Callbacks (optional):
      on_step(step, query, n_new, n_total_unique)
      on_finish(reason, n_total_unique)

    Raises:
      QueryPlanningError — repeated API failures at a given turn.
      SearchFailedError  — loop terminated with zero unique results.
    """
    messages: list[dict] = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT_TEMPLATE.format(as_of=as_of) + language_instruction(lang),
        },
        {"role": "user", "content": _initial_user_turn(ticker, as_of, max_steps)},
    ]
    unique_by_url: dict[str, SearchResult] = {}
    results_by_query: dict[str, list[SearchResult]] = {}
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    steps_used = 0

    for step in range(1, max_steps + 1):
        final_step = step == max_steps
        content = await _ask(client, messages, usage)
        messages.append({"role": "assistant", "content": content})

        call = _parse_tool_call(content)
        if call is None:
            log.warning(f"agent step {step}: unparsable tool call, nudging")
            messages.append({
                "role": "user",
                "content": (
                    "Your previous response was not a valid tool-call JSON object. "
                    'Reply with exactly one object of the form {"tool": "search"|"finish", ...}. '
                    "No prose, no fences."
                ),
            })
            continue

        tool = call.get("tool")

        if tool == "finish":
            reason = _clamp_reason(call.get("reason"))
            steps_used = step
            if on_finish is not None:
                on_finish(reason, len(unique_by_url))
            return _finalize(results_by_query, unique_by_url, steps_used, reason, usage)

        if tool == "search":
            query = str(call.get("query", "")).strip()
            if not query:
                messages.append({
                    "role": "user",
                    "content": "search requires a non-empty 'query'. Try again.",
                })
                continue

            hits = await provider.search(query, num_results=RESULTS_PER_STEP)
            new = [h for h in hits if h.url and h.url not in unique_by_url]
            for h in new:
                unique_by_url[h.url] = h
            results_by_query[query] = hits
            steps_used = step

            if on_step is not None:
                on_step(step, query, len(new), len(unique_by_url))

            messages.append({
                "role": "user",
                "content": _format_tool_result(step, max_steps, query, new, final_step),
            })
            continue

        messages.append({
            "role": "user",
            "content": f"Unknown tool {tool!r}. Use 'search' or 'finish'.",
        })

    # Budget exhausted without an explicit finish — one last forced turn.
    messages.append({
        "role": "user",
        "content": (
            "Step budget exhausted. Respond with exactly:\n"
            '{"tool": "finish", "reason": "<one short sentence, <= 200 chars>"}'
        ),
    })
    content = await _ask(client, messages, usage)
    call = _parse_tool_call(content) or {}
    reason = _clamp_reason(call.get("reason")) or "budget exhausted"
    if on_finish is not None:
        on_finish(reason, len(unique_by_url))
    return _finalize(results_by_query, unique_by_url, max_steps, reason, usage)


def _finalize(
    results_by_query: dict[str, list[SearchResult]],
    unique_by_url: dict[str, SearchResult],
    steps_used: int,
    reason: str,
    usage: dict,
) -> AgentResult:
    if not unique_by_url:
        raise SearchFailedError(
            f"research agent finished with zero unique results after {steps_used} step(s). "
            f"Check the search provider's status/quota or try a different ticker."
        )
    return AgentResult(
        results_by_query=results_by_query,
        steps_used=steps_used,
        finish_reason=reason,
        usage=usage,
    )


def _initial_user_turn(ticker: str, as_of: str, max_steps: int) -> str:
    return (
        f"Ticker: {ticker}\n"
        f"Today: {as_of}\n"
        f"Step budget: {max_steps} searches max.\n\n"
        "Begin research. Emit the first tool call."
    )


def _format_tool_result(
    step: int,
    max_steps: int,
    query: str,
    new_hits: list[SearchResult],
    final_step: bool,
) -> str:
    lines = [f"Tool: search   Query: {query!r}"]
    if not new_hits:
        lines.append("(no new results — consider a different angle, or finish)")
    else:
        lines.append(f"{len(new_hits)} new result(s):")
        for h in new_hits:
            lines.append(_format_hit(h))
    if final_step:
        lines.append(f"\nStep {step}/{max_steps} done. You MUST call finish next.")
    else:
        remaining = max_steps - step
        lines.append(f"\nStep {step}/{max_steps} done. {remaining} left. Continue.")
    return "\n".join(lines)


def _format_hit(h: SearchResult) -> str:
    date = f" ({h.published_date})" if h.published_date else ""
    snippet = (h.snippet or "").strip()[:SNIPPET_TRUNCATE]
    return f"- [{h.title}]{date}\n  {h.url}\n  {snippet}"


def _parse_tool_call(content: str) -> dict | None:
    """Parse a single tool-call JSON object from the model's content.

    Returns None on any parse failure or shape mismatch — the caller will
    nudge the model to retry within the same step budget.
    """
    try:
        data = extract_json(content or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if "tool" not in data:
        return None
    return data


async def _ask(client: AsyncOpenAI, messages: list[dict], usage: dict) -> str:
    """One model turn, with 3 API-level retries. Accumulates token usage."""
    last_err: Exception | None = None
    for attempt in range(1, API_RETRIES + 1):
        try:
            resp = await client.chat.completions.create(
                model=get_model_synthesis(),
                messages=messages,
                temperature=0.1,
                max_tokens=MAX_TOKENS_PER_TURN,
            )
        except Exception as e:
            last_err = e
            log.warning(
                f"agent API call attempt {attempt}/{API_RETRIES} failed: "
                f"{type(e).__name__}: {e}"
            )
            continue
        if resp.usage is not None:
            usage["prompt_tokens"] += resp.usage.prompt_tokens
            usage["completion_tokens"] += resp.usage.completion_tokens
        return resp.choices[0].message.content or ""
    raise QueryPlanningError(
        f"research agent API call failed after {API_RETRIES} attempts: {last_err}"
    )
