import asyncio
import logging
import os
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv
from rich.table import Table

from augur import ui
from augur.aggregator import compute_stats
from augur.personas import filter_personas, load_all
from augur.pipeline import run_pipeline
from augur.report import render_report, write_report
from augur.search import get_provider
from augur.snapshot import QueryPlanningError, SearchFailedError

app = typer.Typer(
    help="Augur — a council of legendary investors, summoned on demand. "
    "Give it a ticker; read the omens.",
)


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
    max_steps: Annotated[
        int | None,
        typer.Option(
            "--max-steps",
            help="Max research-agent steps in Phase 1 "
            "(env AUGUR_MAX_RESEARCH_STEPS, default 8).",
        ),
    ] = None,
    lang: Annotated[
        str,
        typer.Option(
            "--lang",
            help="Output language for narrative/reasoning text (e.g. en, zh, ja, es). "
            "JSON keys and enum values stay in English.",
        ),
    ] = "en",
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
        ui.render_no_search_provider()
        raise typer.Exit(1)

    all_personas = load_all(personas_dir)
    school_list = [s.strip() for s in schools.split(",")] if schools else None
    selected = filter_personas(all_personas, schools=school_list, limit=limit)
    if not selected:
        ui.console.print("[red]No personas matched the filter.[/red]")
        raise typer.Exit(1)

    ui.render_banner(ticker, len(selected), concurrency, provider.name)

    if max_steps is None:
        env_val = os.environ.get("AUGUR_MAX_RESEARCH_STEPS")
        max_steps = int(env_val) if env_val and env_val.isdigit() else 8

    try:
        result = asyncio.run(
            run_pipeline(
                ticker, selected, concurrency, provider, lang,
                max_research_steps=max_steps,
            )
        )
    except QueryPlanningError as e:
        ui.render_error_panel(
            "Query planning failed",
            f"The oracle was silent.\n\n[dim]{e}[/dim]",
            "a different synthesis model, or raise the planner's max_tokens.",
        )
        raise typer.Exit(1) from e
    except SearchFailedError as e:
        alt = "tavily" if provider.name == "exa" else "exa"
        ui.render_error_panel(
            "Search returned no results",
            f"The birds refuse to fly.\n\n[dim]{e}[/dim]",
            f"[cyan]SEARCH_PROVIDER={alt}[/cyan] (with that provider's key "
            f"in .env), or check your quota.",
        )
        raise typer.Exit(1) from e

    stats = compute_stats(result.votes)
    report_md = render_report(
        ticker, result.snapshot, result.votes, stats,
        result.verdict, result.narrative, result.run_stats,
    )
    path = write_report(report_md, out, ticker, result.snapshot.as_of)

    ui.render_final_panel(ticker, stats, result.run_stats, path, result.verdict)


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
    ui.console.print(table)


if __name__ == "__main__":
    app()
