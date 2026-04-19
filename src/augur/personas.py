from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

School = Literal["value", "growth", "macro", "quant", "contrarian"]


class Persona(BaseModel):
    id: str
    name: str
    school: School
    philosophy: str
    key_metrics: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)
    voice: str = ""


def load_all(personas_dir: Path) -> list[Persona]:
    """Load every YAML under personas/**/*.yaml into Persona objects."""
    personas: list[Persona] = []
    seen_ids: set[str] = set()
    for path in sorted(personas_dir.rglob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        persona = Persona.model_validate(data)
        if persona.id in seen_ids:
            raise ValueError(f"duplicate persona id: {persona.id} (from {path})")
        seen_ids.add(persona.id)
        personas.append(persona)
    return personas


def filter_personas(
    personas: list[Persona],
    schools: list[School] | None = None,
    limit: int | None = None,
) -> list[Persona]:
    out = personas
    if schools:
        school_set = set(schools)
        out = [p for p in out if p.school in school_set]
    if limit is not None and limit < len(out):
        out = out[:limit]
    return out


def render_persona_prompt(persona: Persona, ticker: str) -> str:
    """Build the user-turn prompt for a single persona's analysis call."""
    metrics = "\n".join(f"  - {m}" for m in persona.key_metrics) or "  (none specified)"
    avoids = "\n".join(f"  - {a}" for a in persona.avoids) or "  (none specified)"
    return f"""You are {persona.name}, a {persona.school}-school investor.

PHILOSOPHY:
{persona.philosophy}

KEY METRICS YOU CARE ABOUT:
{metrics}

WHAT YOU AVOID:
{avoids}

VOICE:
{persona.voice}

---

TASK: Analyze {ticker} using the market snapshot in your system context.

Apply your philosophy STRICTLY — you are not a generic analyst. Reject frameworks
that clash with your worldview. Reason as {persona.name} would reason.

Produce a PersonaVote with:
- persona_id: "{persona.id}"
- persona_name: "{persona.name}"
- school: "{persona.school}"
- decision: your verdict (action, confidence 0-100, time_horizon, position_sizing, key_reasons, concerns)
- reasoning: 2-3 paragraphs in your voice explaining the decision

Be decisive. No waffling. If the snapshot lacks the data you need, say so in
`concerns` and make your best judgment anyway.
"""
