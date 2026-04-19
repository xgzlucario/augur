"""Rich rendering helpers + playful copy.

All user-facing terminal output lives here. The pipeline module consumes these
through a small set of callbacks so business logic stays CLI-agnostic.
"""

from __future__ import annotations

import random
from contextlib import contextmanager
from pathlib import Path

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from augur.personas import Persona
from augur.schemas import PersonaVote, RunStats

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


# ---------- Renderers ----------


def render_banner(ticker: str, n_personas: int, concurrency: int, provider_name: str) -> None:
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


def render_phase_rule(phase: str, quips: list[str]) -> None:
    console.print(Rule(f"[bold]{phase} · {random.choice(quips)}[/bold]", style="cyan"))


@contextmanager
def transient_spinner(description: str):
    """Rich spinner that clears itself when the block exits."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(description, total=None)
        yield


def render_planned_queries(provider_name: str, queries: list[str]) -> None:
    if not queries:
        return
    console.print(Text.assemble(
        ("  ", ""),
        ("📜 ", ""),
        (f"Planned {len(queries)} ", "dim"),
        (f"{provider_name} ", "bold cyan"),
        ("queries:", "dim"),
    ))
    for i, q in enumerate(queries, 1):
        console.print(Text.assemble(
            (f"     {i}. ", "dim cyan"),
            (q, "italic"),
        ))


def render_search_summary(total_hits: int, n_queries: int) -> None:
    avg = total_hits / n_queries if n_queries else 0
    console.print(Text.assemble(
        ("  ", ""),
        ("🔎 ", ""),
        (f"Got {total_hits} results ", "bold green"),
        (f"across {n_queries} queries (avg {avg:.1f}/query)", "dim"),
    ))


def render_snapshot_summary(ticker: str, as_of: str, n_news: int) -> None:
    console.print(
        f"  [dim]•[/dim] [cyan]{ticker}[/cyan] as of [bold]{as_of}[/bold] "
        f"— fundamentals, price, sector, macro, {n_news} news item(s)"
    )
    console.print()


def render_council_preamble(n_personas: int, concurrency: int) -> None:
    console.print(
        f"[dim]{n_personas} masters take the auspices "
        f"(up to {concurrency} at once)...[/dim]\n"
    )


@contextmanager
def council_progress(total: int):
    """Live progress bar + spinner for Phase 2.

    Yields a `step(persona, vote)` callback. Each call advances the bar and
    prints the vote line above the live display — so finished votes scroll
    normally, the bar stays pinned at the bottom, and the clock keeps ticking.
    """
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Council deliberating"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )
    task_id = progress.add_task("", total=total)
    with progress:
        def step(persona, vote) -> None:
            progress.console.print(_vote_line(persona, vote))
            progress.advance(task_id)
        yield step


def _vote_line(persona, vote):
    if vote is None:
        return Text.assemble(
            ("  💀 ", "dim"),
            (f"{persona.name:<24}", "dim strike"),
            (f"[{persona.school}]".ljust(14), "dim"),
            ("failed to vote", "red dim"),
        )
    color, icon = _action_style(vote.decision.action)
    action = vote.decision.action.upper()
    reason = (vote.decision.key_reasons[0] if vote.decision.key_reasons else "")[:70]
    return Text.assemble(
        (f"  {icon} ", ""),
        (f"{persona.name:<24}", "bold"),
        (f"[{persona.school}]".ljust(14), "dim cyan"),
        (f"{action:<5}", f"bold {color}"),
        ("  ", ""),
        (f"— {reason}" if reason else "", "dim italic"),
    )


def render_vote_line(persona: Persona, vote: PersonaVote | None) -> None:
    console.print(_vote_line(persona, vote))


def render_council_summary(n_success: int, n_total: int, duration: float) -> None:
    console.print()
    console.print(f"[dim]  {n_success}/{n_total} votes cast in {duration:.1f}s[/dim]")
    console.print()


def render_final_panel(
    ticker: str,
    stats: dict,
    run_stats: RunStats,
    report_path: Path,
    verdict: str,
) -> None:
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

    body_parts: list = [Text.from_markup(headline, justify="center")]
    if verdict:
        body_parts.append(Text(""))
        body_parts.append(Text(f"“{verdict}”", style="italic", justify="center"))
    body_parts.extend([
        Text(""),
        verdict_table,
        Text(""),
        stats_table,
    ])
    console.print()
    console.print(Panel(
        Group(*body_parts),
        title=f"[bold]The Augury — {ticker}[/bold]",
        border_style="magenta",
        padding=(1, 2),
    ))


def render_error_panel(title: str, body: str, hint: str) -> None:
    console.print()
    console.print(Panel(
        f"[red]{body}[/red]\n\n[yellow]Try:[/yellow] {hint}",
        title=f"[bold red]{title}[/bold red]",
        border_style="red",
        padding=(1, 2),
    ))


def render_no_search_provider() -> None:
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
