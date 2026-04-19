"""Lenient JSON extraction — some OpenAI-compatible providers wrap JSON in
markdown fences despite being asked not to. This helper strips them.
"""

from __future__ import annotations

import json
from typing import Any


def extract_json(text: str) -> Any:
    """Parse JSON from text, tolerating ```json ... ``` fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
    if text.endswith("```"):
        text = text.removesuffix("```").strip()
    return json.loads(text)
