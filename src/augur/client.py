import os

from dotenv import load_dotenv
from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """Return a cached AsyncOpenAI client configured from env vars.

    Reads:
      OPENAI_API_KEY     (required)
      OPENAI_BASE_URL    (optional — override for OpenAI-compatible providers)
    """
    global _client
    if _client is None:
        load_dotenv()
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Copy .env.example to .env and fill it in."
            )
        base_url = os.environ.get("OPENAI_BASE_URL") or None
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client


def get_model_research() -> str:
    """Model ID for persona fan-out (cheap, fast, runs N times)."""
    model = os.environ.get("OPENAI_MODEL_RESEARCH")
    if not model:
        raise RuntimeError("OPENAI_MODEL_RESEARCH not set. See .env.example.")
    return model


def get_model_synthesis() -> str:
    """Model ID for snapshot + aggregator (stronger, runs twice per run)."""
    model = os.environ.get("OPENAI_MODEL_SYNTHESIS")
    if not model:
        raise RuntimeError("OPENAI_MODEL_SYNTHESIS not set. See .env.example.")
    return model
