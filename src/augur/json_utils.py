"""Lenient JSON extraction — some OpenAI-compatible providers ignore
`response_format={"type": "json_object"}` or wrap JSON in markdown fences
despite being asked not to. This helper extracts the JSON blob regardless.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> Any:
    """Parse JSON from text, tolerating markdown fences and surrounding prose.

    Strategy:
      1. Direct parse — fast path for well-behaved providers.
      2. Strip ```json``` or ``` fences and retry.
      3. Slice from the first '{' to the matching last '}' and retry.

    Raises json.JSONDecodeError if nothing parses.
    """
    text = (text or "").strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown fence
    match = _FENCE_RE.search(text)
    if match:
        inner = match.group(1).strip()
        try:
            return json.loads(inner)
        except json.JSONDecodeError:
            pass

    # 3. Brace-slice: grab from first { to last } and try
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last > first:
        candidate = text[first : last + 1]
        return json.loads(candidate)  # let the final failure surface

    raise json.JSONDecodeError("no JSON object found in text", text, 0)
