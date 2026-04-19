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


# ISO-ish code → human-readable name the model will recognize.
# Unknown codes pass through so users can write any language name directly
# (e.g. --lang "Brazilian Portuguese").
_LANG_NAMES = {
    "en": "English",
    "zh": "Chinese (Simplified, 简体中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ru": "Russian",
}


def language_instruction(lang: str) -> str:
    """One-line directive appended to every system prompt.

    Returns empty string for English / en so the default prompt stays untouched.
    """
    key = lang.strip().lower()
    if not key or key in ("en", "english"):
        return ""
    name = _LANG_NAMES.get(key, lang.strip())
    return (
        f"\n\nLANGUAGE: Write every free-text field in {name}. This includes "
        f"narrative prose, reasoning, key_reasons, concerns, and any summary "
        f"strings. Keep JSON keys, enum values (buy/hold/sell, short/medium/long, "
        f"none/small/medium/large), and ticker symbols in English."
    )
