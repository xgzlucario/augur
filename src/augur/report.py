from datetime import datetime
from pathlib import Path

from augur.schemas import PersonaVote, RunStats, Snapshot

DISCLAIMER = (
    "> **Disclaimer:** This report is a simulation of historical investor personas "
    "for research and educational purposes only. It is not financial advice. "
    "Do not use it to make trading decisions."
)


def _render_stats_section(stats: dict) -> str:
    total = stats["total"]
    by_action = stats["by_action"]
    pct = {k: (v / total * 100 if total else 0) for k, v in by_action.items()}

    lines = ["## Vote Distribution\n"]
    lines.append(f"**{total} personas voted.**\n")
    lines.append("| Action | Count | Share |")
    lines.append("|--------|-------|-------|")
    for action in ("buy", "hold", "sell"):
        count = by_action.get(action, 0)
        lines.append(f"| {action.upper()} | {count} | {pct.get(action, 0):.0f}% |")

    lines.append("\n## By School\n")
    lines.append("| School | Buy | Hold | Sell |")
    lines.append("|--------|-----|------|------|")
    for school, counts in sorted(stats["by_school"].items()):
        lines.append(
            f"| {school} | {counts.get('buy', 0)} | {counts.get('hold', 0)} | "
            f"{counts.get('sell', 0)} |"
        )

    if stats["top_reasons"]:
        lines.append("\n## Top Reasons Cited\n")
        for reason, count in stats["top_reasons"]:
            lines.append(f"- ({count}×) {reason}")

    if stats["top_concerns"]:
        lines.append("\n## Top Concerns Cited\n")
        for concern, count in stats["top_concerns"]:
            lines.append(f"- ({count}×) {concern}")

    return "\n".join(lines)


def _render_vote_roster(votes: list[PersonaVote]) -> str:
    lines = ["## Individual Votes\n"]
    # Group by school for readability
    by_school: dict[str, list[PersonaVote]] = {}
    for v in votes:
        by_school.setdefault(v.school, []).append(v)
    for school in sorted(by_school.keys()):
        lines.append(f"\n### {school.title()} school\n")
        for v in by_school[school]:
            d = v.decision
            lines.append(
                f"**{v.persona_name}** — **{d.action.upper()}**\n"
            )
            lines.append(f"*Reasons:* {'; '.join(d.key_reasons)}  ")
            if d.concerns:
                lines.append(f"*Concerns:* {'; '.join(d.concerns)}  ")
            lines.append(f"\n{v.reasoning}\n")
    return "\n".join(lines)


def render_report(
    ticker: str,
    snapshot: Snapshot,
    votes: list[PersonaVote],
    stats: dict,
    verdict: str,
    narrative: str,
    run_stats: RunStats,
) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    parts = [
        f"# The Augury — {ticker}",
        f"*Generated {generated}. Snapshot as of {snapshot.as_of}.*\n",
        DISCLAIMER,
    ]
    if verdict:
        parts.extend(["\n## Verdict\n", f"> **{verdict}**\n"])
    parts.extend([
        "\n## Synthesis\n",
        narrative,
        "\n",
        _render_stats_section(stats),
        "\n## Market Snapshot\n",
        f"**Fundamentals:** {snapshot.fundamentals}\n",
        f"**Price Action:** {snapshot.price_action}\n",
        f"**Sector Context:** {snapshot.sector_context}\n",
        f"**Macro Context:** {snapshot.macro_context}\n",
        "**Recent News:**",
        *(f"- {n}" for n in snapshot.recent_news),
        "\n",
        _render_vote_roster(votes),
        "\n---\n## Run Stats\n",
        f"- Duration: {run_stats.duration_seconds:.1f}s",
        f"- Personas attempted: {len(votes) + len(run_stats.failed_personas)}",
        f"- Successful votes: {len(votes)}",
        f"- Failed personas: {', '.join(run_stats.failed_personas) if run_stats.failed_personas else 'none'}",
        f"- Total prompt tokens: {run_stats.total_input_tokens:,}",
        f"- Total completion tokens: {run_stats.total_output_tokens:,}",
    ])
    return "\n".join(parts)


def write_report(
    report_markdown: str,
    out_dir: Path,
    ticker: str,
    as_of: str,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{ticker}_{as_of}.md"
    path = out_dir / filename
    path.write_text(report_markdown, encoding="utf-8")
    return path
