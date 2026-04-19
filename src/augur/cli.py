import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from augur.aggregator import compute_stats, synthesize_narrative
from augur.analyst import build_system_message, run_persona
from augur.client import get_client
from augur.personas import Persona, filter_personas, load_all
from augur.report import render_report, write_report
from augur.schemas import PersonaVote, RunStats
from augur.search import get_provider
from augur.snapshot import QueryPlanningError, SearchFailedError, build_snapshot

app = typer.Typer(
    help="Augur — a council of legendary investors, summoned on demand. "
    "Give it a ticker; read the omens.",
)
console = Console()


# ---------- Playful copy ----------

BANNER = r"""
 █████╗ ██╗   ██╗ ██████╗ ██╗   ██╗██████╗
██╔══██╗██║   ██║██╔════╝ ██║   ██║██╔══██╗
███████║██║   ██║██║  ███╗██║   ██║██████╔╝
██╔══██║██║   ██║██║   ██║██║   ██║██╔══██╗
██║  ██║╚██████╔╝╚██████╔╝╚██████╔╝██║  ██║
╚═╝  ╚═╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝
    a council of masters, summoned on demand
"""

GATHER_PROVERBS = [
    "\"The market can stay irrational longer than you can stay solvent.\" — Keynes",
    "\"Price is what you pay; value is what you get.\" — Buffett",
    "\"The big money is not in the buying and selling, but in the waiting.\" — Munger",
    "\"It's not whether you're right or wrong, but how much you make when right.\" — Soros",
    "\"The four most dangerous words in investing are: this time it's different.\" — Templeton",
    "\"In Rome, the augur read the flight of birds. We read the tape.\" — an augur",
]

SNAPSHOT_QUIPS = [
    "Watching the flight of birds over the market.",
    "Reading the tape; peering into filings.",
    "Casting the auspices.",
    "Listening for whispers on the street.",
    "Taking the measure of the market.",
]

DELIBERATION_QUIPS = [
    "Each master retreats to their own study.",
    "The room goes quiet. Only turning pages.",
    "Decades of conviction, compressed into seconds.",
    "The augurs read the signs, each alone.",
    "Pens scratch. Paper rustles. No one speaks.",
]

AUGURY_QUIPS = [
    "The editor compiles the minutes.",
    "The augury is transcribed.",
    "The council's verdict, put to paper.",
]


def _action_style(action: str) -> tuple[str, str]:
    return {
        "buy": ("green", "🟢"),
        "hold": ("yellow", "🟡"),
        "sell": ("red", "🔴"),
    }.get(action, ("white", "⚪"))


# ---------- Rendering helpers ----------


def _render_banner(ticker: str, n_personas: int, concurrency: int, provider_name: str) -> None:
    console.print(Text(BANNER, style="bold magenta"))
    subtitle = Table.grid(padding=(0, 2))
    subtitle.add_column(style="dim")
    subtitle.add_column(style="bold")
    subtitle.add_row("Ticker", f"[cyan]{ticker}[/cyan]")
    subtitle.add_row("Council size", f"{n_personas} personas")
    subtitle.add_row("Concurrency", f"{concurrency}")
    subtitle.add_row("Web search", f"[green]via {provider_name}[/green]")
    console.print(subtitle)
    console.print()
    console.print(Panel(
        f"[italic]{random.choice(GATHER_PROVERBS)}[/italic]",
        border_style="dim",
        padding=(0, 2),
    ))
    console.print()


def _render_vote_line(persona: Persona, vote: PersonaVote | None) -> Text:
    if vote is None:
        return Text.assemble(
            ("  💀 ", "dim"),
            (f"{persona.name:<24}", "dim strike"),
            (f"[{persona.school}]".ljust(14), "dim"),
            ("failed to vote", "red dim"),
        )
    color, icon = _action_style(vote.decision.action)
    action = vote.decision.action.upper()
    conf = vote.decision.confidence
    reason = (vote.decision.key_reasons[0] if vote.decision.key_reasons else "")[:55]
    return Text.assemble(
        (f"  {icon} ", ""),
        (f"{persona.name:<24}", "bold"),
        (f"[{persona.school}]".ljust(14), "dim cyan"),
        (f"{action:<5}", f"bold {color}"),
        ("  conf ", "dim"),
        (f"{conf:>3}", color),
        ("  ", ""),
        (f"— {reason}" if reason else "", "dim italic"),
    )


def _render_final_panel(
    ticker: str,
    stats: dict,
    run_stats: RunStats,
    report_path: Path,
) -> Panel:
    total = stats["total"]
    by_action = stats["by_action"]
    buy = by_action.get("buy", 0)
    hold = by_action.get("hold", 0)
    sell = by_action.get("sell", 0)

    def _pct(n: int) -> str:
        return f"{(n / total * 100) if total else 0:.0f}%"

    verdict_table = Table.grid(padding=(0, 1))
    verdict_table.add_column(style="bold")
    verdict_table.add_column(justify="right")
    verdict_table.add_column(style="dim", justify="right")
    verdict_table.add_row("[green]🟢 BUY[/green]", str(buy), _pct(buy))
    verdict_table.add_row("[yellow]🟡 HOLD[/yellow]", str(hold), _pct(hold))
    verdict_table.add_row("[red]🔴 SELL[/red]", str(sell), _pct(sell))

    majority = max(buy, hold, sell)
    if majority == 0:
        headline = "[dim]No votes collected.[/dim]"
    elif total and majority / total >= 0.75:
        winner = max(by_action, key=by_action.get)
        color, icon = _action_style(winner)
        headline = f"{icon} Strong consensus: [{color} bold]{winner.upper()}[/{color} bold]"
    elif total and majority / total >= 0.5:
        winner = max(by_action, key=by_action.get)
        color, icon = _action_style(winner)
        headline = f"{icon} Lean: [{color} bold]{winner.upper()}[/{color} bold]"
    else:
        headline = "⚖️  [bold]The council is split.[/bold]"

    stats_table = Table.grid(padding=(0, 1))
    stats_table.add_column(style="dim")
    stats_table.add_column()
    stats_table.add_row("Duration", f"{run_stats.duration_seconds:.1f}s")
    stats_table.add_row(
        "Tokens",
        f"{run_stats.total_input_tokens:,} prompt / "
        f"{run_stats.total_output_tokens:,} completion",
    )
    if run_stats.failed_personas:
        stats_table.add_row(
            "Failed", f"[yellow]{len(run_stats.failed_personas)}[/yellow]"
        )
    stats_table.add_row("Report", f"[link=file://{report_path}]{report_path}[/link]")

    body = Group(
        Text.from_markup(headline, justify="center"),
        Text(""),
        verdict_table,
        Text(""),
        stats_table,
    )
    return Panel(
        body,
        title=f"[bold]The Augury — {ticker}[/bold]",
        border_style="magenta",
        padding=(1, 2),
    )


# ---------- The single async pipeline ----------


async def _pipeline(
    ticker: str,
    personas: list[Persona],
    concurrency: int,
    provider: "object",
) -> tuple[list[PersonaVote], RunStats, str, "object"]:
    client = get_client()
    t_start = time.time()

    # Phase 1: snapshot
    console.print(Rule(
        f"[bold]Phase 1 · {random.choice(SNAPSHOT_QUIPS)}[/bold]", style="cyan",
    ))

    def _show_queries(queries: list[str]) -> None:
        if not queries:
            return
        header = Text.assemble(
            ("  ", ""),
            ("📜 ", ""),
            (f"Planned {len(queries)} ", "dim"),
            (f"{provider.name} ", "bold cyan"),
            ("queries:", "dim"),
        )
        console.print(header)
        for i, q in enumerate(queries, 1):
            console.print(Text.assemble(
                (f"     {i}. ", "dim cyan"),
                (q, "italic"),
            ))

    def _show_search_results(total_hits: int, n_queries: int) -> None:
        avg = total_hits / n_queries if n_queries else 0
        console.print(Text.assemble(
            ("  ", ""),
            ("🔎 ", ""),
            (f"Got {total_hits} results ", "bold green"),
            (f"across {n_queries} queries (avg {avg:.1f}/query)", "dim"),
        ))

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        t = progress.add_task(
            f"[cyan]Reading the signs via {provider.name}...",
            total=None,
        )
        snapshot = await build_snapshot(
            client,
            ticker,
            search_provider=provider,
            on_queries=_show_queries,
            on_search_results=_show_search_results,
        )
        progress.update(t, description=f"[green]✔ Snapshot ready — {snapshot.as_of}")
        progress.stop_task(t)

    console.print(
        f"  [dim]•[/dim] [cyan]{ticker}[/cyan] as of [bold]{snapshot.as_of}[/bold] "
        f"— fundamentals, price, sector, macro, "
        f"{len(snapshot.recent_news)} news item(s)"
    )
    console.print()

    # Phase 2: council voting — print each vote as it comes in
    console.print(Rule(
        f"[bold]Phase 2 · {random.choice(DELIBERATION_QUIPS)}[/bold]", style="cyan",
    ))
    console.print(
        f"[dim]{len(personas)} masters take the auspices "
        f"(up to {concurrency} at once)...[/dim]\n"
    )

    system_message = build_system_message(snapshot)
    sem = asyncio.Semaphore(concurrency)
    votes: list[PersonaVote] = []
    usage_records: list[dict] = []
    failed_ids: list[str] = []
    t_phase2_start = time.time()

    async def _one(p: Persona) -> None:
        async with sem:
            vote, usage = await run_persona(client, p, ticker, system_message)
            if vote is not None:
                votes.append(vote)
            else:
                failed_ids.append(p.id)
            if usage:
                usage_records.append(usage)
            console.print(_render_vote_line(p, vote))

    # Prime the cache with the first persona, then fan the rest out concurrently
    if personas:
        await _one(personas[0])
        if len(personas) > 1:
            await asyncio.gather(*(_one(p) for p in personas[1:]))

    phase2_duration = time.time() - t_phase2_start
    n_success = len(votes)
    console.print()
    console.print(
        f"[dim]  {n_success}/{len(personas)} votes cast in "
        f"{phase2_duration:.1f}s[/dim]"
    )
    console.print()

    # Phase 3: synthesis
    console.print(Rule(
        f"[bold]Phase 3 · {random.choice(AUGURY_QUIPS)}[/bold]", style="cyan",
    ))
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as ag_progress:
        t = ag_progress.add_task(
            "[cyan]Transcribing the augury...", total=None
        )
        narrative = await synthesize_narrative(client, ticker, snapshot, votes)
        ag_progress.update(t, description="[green]✔ Augury complete")
        ag_progress.stop_task(t)

    run_stats = RunStats(
        total_input_tokens=sum(u.get("prompt_tokens", 0) for u in usage_records),
        total_output_tokens=sum(u.get("completion_tokens", 0) for u in usage_records),
        failed_personas=failed_ids,
        duration_seconds=time.time() - t_start,
    )
    return votes, run_stats, narrative, snapshot


# ---------- Commands ----------


def _default_personas_dir() -> Path:
    """Locate the personas/ directory across install modes.

    Priority:
      1. Bundled inside the installed package (src/augur/personas in the wheel,
         placed there by hatch's force-include).
      2. Sibling of the source tree — editable / dev install where personas/
         lives at the repo root.
    """
    bundled = Path(__file__).resolve().parent / "personas"
    if bundled.is_dir():
        return bundled
    # Fall back to the repo-root personas/ (editable install / running from source)
    return Path(__file__).resolve().parent.parent.parent / "personas"


@app.command()
def run(
    ticker: Annotated[str, typer.Argument(help="Ticker symbol, e.g. AAPL")],
    limit: Annotated[int | None, typer.Option(help="Max personas to use")] = None,
    schools: Annotated[
        str | None,
        typer.Option(help="Comma-separated school filter: value,growth,macro,quant,contrarian"),
    ] = None,
    personas_dir: Annotated[
        Path | None, typer.Option(help="Directory with persona YAMLs")
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Output directory for reports")] = None,
    concurrency: Annotated[int, typer.Option(help="Max concurrent persona calls")] = 10,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="Debug logging")] = False,
) -> None:
    """Convene the council, read the omens, write the augury."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    ticker = ticker.upper()
    personas_dir = personas_dir or _default_personas_dir()
    out = out or (Path.cwd() / "reports")
    load_dotenv()

    provider = get_provider()
    if provider is None:
        console.print(Panel(
            "[red]No omens without eyes.[/red] Augur needs a search key — "
            "the LLM's training data is too stale for this game.\n\n"
            "[yellow]Add either to your .env:[/yellow]\n"
            "  [cyan]EXA_API_KEY[/cyan]     https://exa.ai\n"
            "  [cyan]TAVILY_API_KEY[/cyan]  https://tavily.com",
            title="[bold red]Web search required[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))
        raise typer.Exit(1)

    all_personas = load_all(personas_dir)
    school_list = [s.strip() for s in schools.split(",")] if schools else None
    selected = filter_personas(all_personas, schools=school_list, limit=limit)
    if not selected:
        console.print("[red]No personas matched the filter.[/red]")
        raise typer.Exit(1)

    _render_banner(ticker, len(selected), concurrency, provider.name)

    try:
        votes, run_stats, narrative, snapshot = asyncio.run(
            _pipeline(ticker, selected, concurrency, provider)
        )
    except QueryPlanningError as e:
        console.print()
        console.print(Panel(
            f"[red]The oracle was silent.[/red]\n\n"
            f"[dim]{e}[/dim]\n\n"
            f"[yellow]Try:[/yellow] a different synthesis model, "
            f"or raise the planner's max_tokens.",
            title="[bold red]Query planning failed[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))
        raise typer.Exit(1) from e
    except SearchFailedError as e:
        alt = "tavily" if provider.name == "exa" else "exa"
        console.print()
        console.print(Panel(
            f"[red]The birds refuse to fly.[/red]\n\n"
            f"[dim]{e}[/dim]\n\n"
            f"[yellow]Try:[/yellow] [cyan]SEARCH_PROVIDER={alt}[/cyan] "
            f"(with that provider's key in .env), or check your quota.",
            title="[bold red]Search returned no results[/bold red]",
            border_style="red",
            padding=(1, 2),
        ))
        raise typer.Exit(1) from e

    stats = compute_stats(votes)
    report_md = render_report(ticker, snapshot, votes, stats, narrative, run_stats)
    path = write_report(report_md, out, ticker, snapshot.as_of)

    console.print()
    console.print(_render_final_panel(ticker, stats, run_stats, path))


@app.command()
def list_personas(
    personas_dir: Annotated[
        Path | None, typer.Option(help="Directory with persona YAMLs")
    ] = None,
) -> None:
    """List all loaded personas, grouped by school."""
    personas_dir = personas_dir or _default_personas_dir()
    personas = load_all(personas_dir)
    by_school: dict[str, list] = {}
    for p in personas:
        by_school.setdefault(p.school, []).append(p)

    table = Table(title=f"Loaded Personas ({len(personas)} total)", border_style="cyan")
    table.add_column("School", style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    for school in sorted(by_school.keys()):
        for i, p in enumerate(by_school[school]):
            table.add_row(school if i == 0 else "", p.id, p.name)
        table.add_section()
    console.print(table)


if __name__ == "__main__":
    app()
