from typing import Literal

from pydantic import BaseModel, Field

Action = Literal["buy", "hold", "sell"]


class Snapshot(BaseModel):
    ticker: str
    as_of: str
    fundamentals: str = Field(description="P/E, revenue, margins, balance sheet highlights")
    recent_news: list[str] = Field(description="Key news from the last 30 days")
    price_action: str = Field(description="Recent price trend and volume commentary")
    sector_context: str = Field(description="How the stock compares to its sector/peers")
    macro_context: str = Field(description="Relevant macro backdrop (rates, cycle, FX, geopolitics)")


class Decision(BaseModel):
    action: Action
    key_reasons: list[str] = Field(max_length=5, min_length=1)
    concerns: list[str] = Field(max_length=3)


class PersonaVote(BaseModel):
    persona_id: str
    persona_name: str
    school: str
    decision: Decision
    reasoning: str = Field(description="2-3 paragraphs of persona-voice narrative")


class RunStats(BaseModel):
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    failed_personas: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    research_steps: int = 0
