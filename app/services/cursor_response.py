"""
Parse JSON returned from Cursor chat for the copy-paste CV tailoring workflow.

Keeps fence-stripping and validation in one place so API routes stay thin.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict


def strip_json_fences(text: str) -> str:
    """Remove optional ```json ... ``` wrapper around pasted model output."""
    s = text.strip()
    m = re.match(r"^```(?:json)?\s*\r?\n?(.*?)\r?\n?```\s*$", s, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else s


def parse_cursor_response_json(
    response_text: str, *, require_cover: bool = True
) -> Dict[str, str]:
    """
    Parse Cursor chat response JSON and extract tailored markdown fields.

    Args:
        response_text: Raw paste from Cursor (may include markdown fences).
        require_cover: When True, ``tailored_cover_markdown`` must be non-empty.

    Returns:
        Dict with keys ``tailored_cv_markdown`` and ``tailored_cover_markdown``.

    Raises:
        ValueError: If JSON is invalid or required fields are missing.
    """
    raw = strip_json_fences(response_text)
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Response is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("Response JSON must be an object.")
    cv = parsed.get("tailored_cv_markdown")
    cover = parsed.get("tailored_cover_markdown")
    if not isinstance(cv, str) or not cv.strip():
        raise ValueError("Missing or invalid 'tailored_cv_markdown'.")
    if require_cover:
        if not isinstance(cover, str) or not cover.strip():
            raise ValueError("Missing or invalid 'tailored_cover_markdown'.")
        cover_out = cover.strip()
    else:
        cover_out = cover.strip() if isinstance(cover, str) and cover.strip() else ""
    return {
        "tailored_cv_markdown": cv.strip(),
        "tailored_cover_markdown": cover_out,
    }
