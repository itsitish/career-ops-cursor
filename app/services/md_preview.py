"""
Safe HTML preview for tailored CV/cover markdown in the dashboard.

Escapes all text, then applies a small subset of Markdown (headings, lists,
horizontal rules, ``**bold**``). No raw HTML passthrough from the model.
"""

from __future__ import annotations

import html
import re
from typing import List

# Remove C0 controls except tab / LF / CR so browser DOM and JSON stay stable.
_BAD_CHARS = dict.fromkeys(
    [i for i in range(32) if i not in (9, 10, 13)] + [127]
)

# Setext-style or thematic breaks (---, ***, ___).
_HR = re.compile(r"^\s*([-*_])\1\1+\s*$")
# Allow ``###Title`` (no space) as well as ``### Title``.
_HEADING = re.compile(r"^(#{1,3})\s*(.+)$")
_BULLET = re.compile(r"^\s*-\s+(.+)$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _inline_bold(escaped_line: str) -> str:
    """Convert ``**...**`` to <strong> on an already HTML-escaped line."""
    return _BOLD.sub(r"<strong>\1</strong>", escaped_line)


def tailor_markdown_to_safe_html(markdown: str) -> str:
    """
    Build safe HTML for in-app preview of tailored documents.

    Args:
        markdown: Source markdown (CV or cover).

    Returns:
        HTML fragment (no outer wrapper). Empty string if input is blank.
    """
    if not markdown or not str(markdown).strip():
        return ""

    text = str(markdown).translate(_BAD_CHARS)
    lines = text.replace("\r\n", "\n").split("\n")
    out: List[str] = []
    in_ul = False

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if _HR.match(line):
            if in_ul:
                out.append("</ul>")
                in_ul = False
            out.append("<hr/>")
            continue

        if not stripped:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            continue

        hm = _HEADING.match(stripped)
        if hm:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            level = len(hm.group(1))
            title = hm.group(2).strip()
            inner = _inline_bold(html.escape(title))
            out.append(f'<h{level} class="tailor-md-h">{inner}</h{level}>')
            continue

        bm = _BULLET.match(line)
        if bm:
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            item = bm.group(1).strip()
            out.append(f"<li>{_inline_bold(html.escape(item))}</li>")
            continue

        if in_ul:
            out.append("</ul>")
            in_ul = False

        out.append(f"<p>{_inline_bold(html.escape(stripped))}</p>")

    if in_ul:
        out.append("</ul>")

    return "\n".join(out)
