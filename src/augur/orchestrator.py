import asyncio
import time
from typing import Callable

from rich.progress import Progress

from augur.analyst import build_system_message, run_persona
from augur.client import get_client
from augur.personas import Persona
from augur.schemas import PersonaVote, RunStats, Snapshot
from augur.search import SearchProvider, get_provider
from augur.snapshot import build_snapshot


async def run_council(
    ticker: str,
    personas: list[Persona],
    concurrency: int = 10,
    progress: Progress | None = None,
    search_enabled: bool = True,
    on_vote: Callable[[Persona, PersonaVote | None], None] | None = None,
) -> tuple[Snapshot, list[PersonaVote], RunStats]:
    """End-to-end: build snapshot, fan out persona calls, collect votes.

    If `search_enabled` is True and a search provider is configured via env,
    the snapshot is grounded in live web results. Otherwise falls back to
    LLM-only training knowledge.

    `on_vote` (if provided) is invoked immediately after each persona completes,
    with (persona, vote). `vote` is None when the persona failed. This lets the
    CLI stream per-persona updates without the orchestrator caring about UI.
    """
    client = get_client()
    started = time.time()

    search_provider: SearchProvider | None = get_provider() if search_enabled else None

    # Phase 1: snapshot
    snap_task = None
    if progress is not None:
        label = (
            f"Building market snapshot for {ticker} (via {search_provider.name})..."
            if search_provider
            else f"Building market snapshot for {ticker} (LLM-only)..."
        )
        snap_task = progress.add_task(f"[cyan]{label}", total=None)
    snapshot = await build_snapshot(client, ticker, search_provider=search_provider)
    if progress is not None and snap_task is not None:
        progress.update(snap_task, description=f"[green]Snapshot ready ({snapshot.as_of})")
        progress.stop_task(snap_task)

    # Phase 2: fan-out persona calls. Build the system message ONCE so every
    # persona call sends the exact same bytes — this is what lets the provider's
    # automatic prefix caching (where supported) kick in.
    system_message = build_system_message(snapshot)

    sem = asyncio.Semaphore(concurrency)
    votes: list[PersonaVote] = []
    usage_records: list[dict] = []
    failed_ids: list[str] = []

    council_task = None
    if progress is not None:
        council_task = progress.add_task(
            f"[cyan]Council voting ({len(personas)} personas)...", total=len(personas)
        )

    async def _guarded(p: Persona) -> None:
        async with sem:
            vote, usage = await run_persona(client, p, snapshot, ticker, system_message)
            if vote is not None:
                votes.append(vote)
            else:
                failed_ids.append(p.id)
            if usage:
                usage_records.append(usage)
            if on_vote is not None:
                try:
                    on_vote(p, vote)
                except Exception:
                    pass  # callbacks never break the pipeline
            if progress is not None and council_task is not None:
                progress.update(council_task, advance=1)

    # Prime the cache: run the first persona alone so the provider has a chance
    # to cache the shared prefix, then fan out the rest under the semaphore.
    if personas:
        await _guarded(personas[0])
        if len(personas) > 1:
            await asyncio.gather(*(_guarded(p) for p in personas[1:]))

    duration = time.time() - started
    stats = RunStats(
        total_input_tokens=sum(u.get("prompt_tokens", 0) for u in usage_records),
        total_output_tokens=sum(u.get("completion_tokens", 0) for u in usage_records),
        failed_personas=failed_ids,
        duration_seconds=duration,
    )
    return snapshot, votes, stats
