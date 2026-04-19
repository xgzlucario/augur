"""The three-phase orchestration: snapshot → council → augury.

This module owns the async pipeline. It's UI-agnostic: rendering is delegated
to `augur.ui` helpers. Returns a typed `PipelineResult` rather than a tuple
so callers don't depend on positional order.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from augur import ui
from augur.aggregator import synthesize_narrative
from augur.analyst import build_system_message, run_persona
from augur.client import get_client
from augur.personas import Persona
from augur.schemas import PersonaVote, RunStats, Snapshot
from augur.search import SearchProvider
from augur.snapshot import build_snapshot


@dataclass
class PipelineResult:
    votes: list[PersonaVote]
    run_stats: RunStats
    verdict: str
    narrative: str
    snapshot: Snapshot


async def run_pipeline(
    ticker: str,
    personas: list[Persona],
    concurrency: int,
    provider: SearchProvider,
    lang: str,
) -> PipelineResult:
    client = get_client()
    t_start = time.time()

    # Phase 1: snapshot
    ui.render_phase_rule("Phase 1", ui.SNAPSHOT_QUIPS)
    with ui.transient_spinner(f"[cyan]Reading the signs via {provider.name}..."):
        snapshot = await build_snapshot(
            client,
            ticker,
            search_provider=provider,
            on_queries=lambda qs: ui.render_planned_queries(provider.name, qs),
            on_search_results=ui.render_search_summary,
            lang=lang,
        )
    ui.render_snapshot_summary(ticker, snapshot.as_of, len(snapshot.recent_news))

    # Phase 2: council — stream each vote as it lands
    ui.render_phase_rule("Phase 2", ui.DELIBERATION_QUIPS)
    ui.render_council_preamble(len(personas), concurrency)

    system_message = build_system_message(snapshot, lang=lang)
    sem = asyncio.Semaphore(concurrency)
    votes: list[PersonaVote] = []
    usage_records: list[dict] = []
    failed_ids: list[str] = []
    t_phase2 = time.time()

    async def _one(p: Persona) -> None:
        async with sem:
            vote, usage = await run_persona(client, p, ticker, system_message)
            if vote is not None:
                votes.append(vote)
            else:
                failed_ids.append(p.id)
            if usage:
                usage_records.append(usage)
            ui.render_vote_line(p, vote)

    # Prime any provider-side prefix cache with a single call first, then fan out
    if personas:
        await _one(personas[0])
        if len(personas) > 1:
            await asyncio.gather(*(_one(p) for p in personas[1:]))

    ui.render_council_summary(len(votes), len(personas), time.time() - t_phase2)

    # Phase 3: synthesis
    ui.render_phase_rule("Phase 3", ui.AUGURY_QUIPS)
    with ui.transient_spinner("[cyan]Transcribing the augury..."):
        verdict, narrative = await synthesize_narrative(
            client, ticker, snapshot, votes, lang=lang
        )

    run_stats = RunStats(
        total_input_tokens=sum(u.get("prompt_tokens", 0) for u in usage_records),
        total_output_tokens=sum(u.get("completion_tokens", 0) for u in usage_records),
        failed_personas=failed_ids,
        duration_seconds=time.time() - t_start,
    )
    return PipelineResult(
        votes=votes,
        run_stats=run_stats,
        verdict=verdict,
        narrative=narrative,
        snapshot=snapshot,
    )
