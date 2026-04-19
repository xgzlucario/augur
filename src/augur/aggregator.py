import json
import logging
import re
from collections import Counter, defaultdict

from openai import AsyncOpenAI

from augur.client import get_model_synthesis
from augur.json_utils import extract_json
from augur.schemas import PersonaVote, Snapshot

log = logging.getLogger(__name__)

# Matches `"verdict": "..."` tolerating escaped quotes inside the value.
_VERDICT_RE = re.compile(r'"verdict"\s*:\s*"((?:[^"\\]|\\.)*)"', re.DOTALL)


def _salvage_verdict(text: str) -> str:
    """Extract the verdict string even from truncated / non-JSON content."""
    m = _VERDICT_RE.search(text)
    if not m:
        return ""
    try:
        return json.loads(f'"{m.group(1)}"')
    except json.JSONDecodeError:
        return m.group(1).strip()


def compute_stats(votes: list[PersonaVote]) -> dict:
    """Deterministic, non-LLM stats about the council's verdict."""
    if not votes:
        return {
            "total": 0,
            "by_action": {},
            "by_school": {},
            "top_reasons": [],
            "top_concerns": [],
        }

    action_counts = Counter(v.decision.action for v in votes)
    by_school: dict[str, Counter] = defaultdict(Counter)

    reasons: Counter = Counter()
    concerns: Counter = Counter()

    for v in votes:
        by_school[v.school][v.decision.action] += 1
        reasons.update(r.lower().strip() for r in v.decision.key_reasons)
        concerns.update(c.lower().strip() for c in v.decision.concerns)

    return {
        "total": len(votes),
        "by_action": dict(action_counts),
        "by_school": {school: dict(counts) for school, counts in by_school.items()},
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
            f"(horizon={d.time_horizon}, size={d.position_sizing})\n"
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

OUTPUT RULES (critical):
- Respond with a single JSON object and NOTHING else.
- No markdown fences, no ```json blocks, no prose wrapper.
- Shape: {"verdict": "<one sentence>", "narrative": "<markdown body>"}.
- `verdict` is a single plain-text sentence (<= 180 chars), no markdown, no
  trailing newline. It should capture the council's bottom line AND the main
  nuance (e.g. "Strong buy from value and growth, but macro dissenters flag
  rate risk on a 12-month horizon").
- `narrative` is plain Markdown, concise — aim for ~400-600 words total. Do
  NOT repeat the verdict inside it. Cover: consensus across schools, where
  it fractures, notable contrarian voices, and what would change minds
  (catalysts, data gaps). No preamble, no disclaimer — those are added
  elsewhere.
"""


async def synthesize_narrative(
    client: AsyncOpenAI,
    ticker: str,
    snapshot: Snapshot,
    votes: list[PersonaVote],
) -> tuple[str, str]:
    """Ask the synthesis model for a one-sentence verdict and a narrative.

    Returns (verdict, narrative). If parsing fails we fall back to the raw
    content as the narrative with an empty verdict so the report still renders.
    """
    if not votes:
        return ("", "_No persona votes were collected. Cannot synthesize narrative._")

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
                    "Return the JSON object described in the system prompt."
                ),
            },
        ],
        max_tokens=6000,
    )

    content = (response.choices[0].message.content or "").strip()
    if not content:
        return ("", "_Aggregator returned no text content._")

    try:
        data = extract_json(content)
    except json.JSONDecodeError:
        log.warning("aggregator: JSON parse failed, falling back to raw content")
        return (_salvage_verdict(content), content)

    verdict = (data.get("verdict") or "").strip() if isinstance(data, dict) else ""
    narrative = (data.get("narrative") or "").strip() if isinstance(data, dict) else ""
    if not narrative:
        narrative = content
    if not verdict:
        verdict = _salvage_verdict(content)
    return (verdict, narrative)
