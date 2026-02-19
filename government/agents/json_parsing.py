"""Shared JSON extraction utilities for agent response parsing."""

from __future__ import annotations

import json
import logging
import re

log = logging.getLogger(__name__)

# Follow-up instruction appended to the original prompt on retry.
_RETRY_SUFFIX = (
    "\n\n--- IMPORTANT ---\n"
    "Your previous response did not contain a valid JSON object. "
    "Please respond ONLY with the JSON object as specified in your instructions. "
    "Do not include any preamble, explanation, or markdown formatting — "
    "output the raw JSON object and nothing else."
)

# Kept for backwards compatibility with imports.
RETRY_PROMPT = _RETRY_SUFFIX


def retry_prompt(original_prompt: str) -> str:
    """Build a retry prompt that includes the original context.

    Previous approach sent RETRY_PROMPT alone as a *new* conversation,
    so the model had no context about what to produce.  This version
    re-sends the original prompt with an explicit JSON-only instruction
    appended.
    """
    return original_prompt + _RETRY_SUFFIX


def extract_json(text: str) -> dict[str, object] | None:
    """Try to extract a JSON object from *text*.

    Uses two strategies:
    1. Find the outermost ``{ ... }`` via bracket-counting so nested braces
       are handled correctly.
    2. Fall back to a regex that grabs the first ``{ ... }`` span.

    Returns the parsed dict on success, or ``None`` if no valid JSON object
    could be found.
    """
    if not text:
        return None

    # Strategy 1: bracket-counting for the outermost object.
    result = _extract_by_bracket_counting(text)
    if result is not None:
        return result

    # Strategy 2: greedy regex (less precise but catches more edge cases).
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    return None


def _extract_by_bracket_counting(text: str) -> dict[str, object] | None:
    """Find the outermost ``{ ... }`` using bracket counting."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)  # type: ignore[no-any-return]
                except json.JSONDecodeError:
                    return None
    return None
