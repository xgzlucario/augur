import json
import logging

from openai import AsyncOpenAI

from augur.client import get_model_research, language_instruction
from augur.json_utils import extract_json
from augur.personas import Persona, render_persona_prompt
from augur.schemas import PersonaVote, Snapshot

log = logging.getLogger(__name__)

FRAMEWORK_INSTRUCTIONS = """You are participating in an investment council simulation.

Each persona in the council reasons IN-CHARACTER — they do not pretend to be
balanced or centrist. They apply their specific philosophy, prejudices, and
preferred metrics. A value investor who hates tech should say so. A macro trader
who only cares about rates should ignore fundamentals.

You will receive:
- A MARKET SNAPSHOT (shared across all personas) below in this system prompt.
- A PERSONA BRIEF (your identity + philosophy) in the user turn.

Your job: produce a single PersonaVote as the assigned persona, based on the snapshot.

OUTPUT RULES (critical):
- Respond with a single JSON object and NOTHING else.
- Must match this schema exactly:
  {
    "persona_id": string,
    "persona_name": string,
    "school": string,
    "decision": {
      "action": "buy" | "hold" | "sell",
      "time_horizon": "short" | "medium" | "long",
      "position_sizing": "none" | "small" | "medium" | "large",
      "key_reasons": array of 1-5 strings,
      "concerns": array of up to 3 strings
    },
    "reasoning": string (2-3 paragraphs in your voice)
  }

Do not search the web. Do not ask questions.
"""


def build_system_message(snapshot: Snapshot, lang: str = "en") -> str:
    """Build the system message string. Many OpenAI-compatible providers do
    automatic prefix caching on identical system prompts across requests, so
    keeping this deterministic across persona calls is what gets us cache hits.
    """
    return (
        FRAMEWORK_INSTRUCTIONS
        + language_instruction(lang)
        + "\n\nMARKET SNAPSHOT (shared across all personas):\n"
        + snapshot.model_dump_json(indent=2)
    )


MAX_ATTEMPTS = 3


async def run_persona(
    client: AsyncOpenAI,
    persona: Persona,
    ticker: str,
    system_message: str,
) -> tuple[PersonaVote | None, dict]:
    """Run one persona's analysis with up to MAX_ATTEMPTS retries.

    Returns (vote, usage_dict). Vote is None only after all attempts fail.
    Token usage is summed across attempts so cost accounting stays accurate.

    `system_message` is built once per run (containing the framework + snapshot
    JSON) and reused verbatim across N persona calls — identical prefix bytes
    are the prerequisite for any prefix caching the provider offers.
    """
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0}
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": render_persona_prompt(persona, ticker)},
    ]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = await client.chat.completions.create(
                model=get_model_research(),
                messages=messages,
                max_tokens=6000,
                temperature=0.1,
            )
        except Exception as e:
            log.warning(
                f"persona {persona.id} attempt {attempt}/{MAX_ATTEMPTS} "
                f"API call failed: {type(e).__name__}: {e}"
            )
            continue

        if response.usage is not None:
            total_usage["prompt_tokens"] += response.usage.prompt_tokens
            total_usage["completion_tokens"] += response.usage.completion_tokens

        content = response.choices[0].message.content
        if not content:
            log.warning(
                f"persona {persona.id} attempt {attempt}/{MAX_ATTEMPTS} "
                f"returned empty content"
            )
            continue

        try:
            data = extract_json(content)
            vote = PersonaVote.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            log.warning(
                f"persona {persona.id} attempt {attempt}/{MAX_ATTEMPTS} "
                f"returned unparsable output: {e}"
            )
            continue

        # Force persona fields to match the YAML (defensive — model sometimes drifts)
        vote.persona_id = persona.id
        vote.persona_name = persona.name
        vote.school = persona.school
        return vote, total_usage

    log.warning(f"persona {persona.id} gave up after {MAX_ATTEMPTS} attempts")
    return None, total_usage
