from collections import Counter, defaultdict

from openai import AsyncOpenAI

from augur.client import get_model_synthesis
from augur.schemas import PersonaVote, Snapshot


def compute_stats(votes: list[PersonaVote]) -> dict:
    """Deterministic, non-LLM stats about the council's verdict."""
    if not votes:
        return {
            "total": 0,
            "by_action": {},
            "by_school": {},
            "avg_confidence_by_action": {"buy": 0, "hold": 0, "sell": 0},
            "top_reasons": [],
            "top_concerns": [],
        }

    action_counts = Counter(v.decision.action for v in votes)
    by_school: dict[str, Counter] = defaultdict(Counter)
    confidence_sum: dict[str, int] = defaultdict(int)

    reasons: Counter = Counter()
    concerns: Counter = Counter()

    for v in votes:
        by_school[v.school][v.decision.action] += 1
        confidence_sum[v.decision.action] += v.decision.confidence
        reasons.update(r.lower().strip() for r in v.decision.key_reasons)
        concerns.update(c.lower().strip() for c in v.decision.concerns)

    avg_conf = {
        action: (confidence_sum[action] / action_counts[action]) if action_counts[action] else 0
        for action in ("buy", "hold", "sell")
    }

    return {
        "total": len(votes),
        "by_action": dict(action_counts),
        "by_school": {school: dict(counts) for school, counts in by_school.items()},
        "avg_confidence_by_action": avg_conf,
        "top_reasons": reasons.most_common(5),
        "top_concerns": concerns.most_common(5),
    }


def _format_votes_for_prompt(votes: list[PersonaVote]) -> str:
    """Compact representation of votes for the aggregator LLM."""
    lines = []
    for v in votes:
        d = v.decision
        lines.append(
            f"- {v.persona_name} [{v.school}]: {d.action.upper()} "
            f"(confidence={d.confidence}, horizon={d.time_horizon}, size={d.position_sizing})\n"
            f"  reasons: {'; '.join(d.key_reasons)}\n"
            f"  concerns: {'; '.join(d.concerns) if d.concerns else '(none)'}\n"
        )
    return "\n".join(lines)


AGGREGATOR_SYSTEM = """You are the editor for an investment research publication.

A panel of investors (each with a distinct philosophy) has independently voted
on a ticker. Your job: write a balanced synthesis that surfaces the consensus,
the disagreements, and the most interesting contrarian takes.

The reader wants to understand WHY schools of thought disagree, not a generic
average. Quote specific personas where their reasoning stands out. Be concise
and structured — the deterministic vote statistics are rendered separately.

Output plain Markdown. No preamble, no disclaimer (those are added elsewhere).
"""


async def synthesize_narrative(
    client: AsyncOpenAI,
    ticker: str,
    snapshot: Snapshot,
    votes: list[PersonaVote],
) -> str:
    """Ask the synthesis model to write the narrative section of the report."""
    if not votes:
        return "_No persona votes were collected. Cannot synthesize narrative._"

    votes_text = _format_votes_for_prompt(votes)

    response = await client.chat.completions.create(
        model=get_model_synthesis(),
        messages=[
            {"role": "system", "content": AGGREGATOR_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Ticker: {ticker}\n"
                    f"Snapshot date: {snapshot.as_of}\n\n"
                    f"=== SNAPSHOT ===\n{snapshot.model_dump_json(indent=2)}\n\n"
                    f"=== {len(votes)} COUNCIL VOTES ===\n{votes_text}\n\n"
                    "Write the synthesis. Structure suggestion:\n"
                    "1. The verdict in one sentence\n"
                    "2. Where the council agrees (cross-school consensus)\n"
                    "3. Where it fractures (which schools split and why)\n"
                    "4. Notable contrarian voices worth hearing\n"
                    "5. What would change minds (data gaps, catalysts to watch)\n"
                ),
            },
        ],
        max_tokens=4000,
    )

    content = response.choices[0].message.content or ""
    return content.strip() or "_Aggregator returned no text content._"
