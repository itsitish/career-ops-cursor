"""
PDF export helper for tailored CV/Cover markdown text.

Splits content into a centered header (contact block up to GitHub line, or a short
fallback prefix) and a left-aligned body. Supports markdown headings, inline **bold**,
and ATS-safe ASCII punctuation replacements.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from fpdf import FPDF


OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "resumes"


def _ats_clean(markdown_text: str) -> str:
    """Replace common Unicode punctuation with ASCII for ATS-safe output."""
    return (
        markdown_text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _split_bold_segments(line: str) -> list[tuple[bool, str]]:
    """
    Split a line by ``**``; odd-index parts (1, 3, ...) are bold.
    An odd number of ``**`` leaves trailing text non-bold.
    """
    parts = line.split("**")
    return [(i % 2 == 1, p) for i, p in enumerate(parts)]


def _looks_like_name(line: str) -> bool:
    """Heuristic: short first line without URLs, not a markdown heading."""
    s = line.strip()
    if not s or s.startswith("#"):
        return False
    if "http" in s.lower():
        return False
    return len(s) <= 50


def _split_header_body(lines: list[str]) -> tuple[list[str], list[str]]:
    """
    Header: from start through first line containing ``github`` (case-insensitive),
    inclusive. If none: lines before first ``## `` (exclusive), capped at 10 lines.
    """
    n = len(lines)
    for i, line in enumerate(lines):
        if "github" in line.lower():
            return lines[: i + 1], lines[i + 1 :]

    first_h2: int | None = None
    for j, line in enumerate(lines):
        if line.startswith("## "):
            first_h2 = j
            break
    end = min(first_h2 if first_h2 is not None else n, 10, n)
    return lines[:end], lines[end:]


def _words_from_segments(segments: Iterable[tuple[bool, str]]) -> list[tuple[bool, str]]:
    """Turn (bold, chunk) segments into (bold, word) tokens."""
    out: list[tuple[bool, str]] = []
    for bold, chunk in segments:
        if not chunk:
            continue
        parts = chunk.split()
        for w in parts:
            out.append((bold, w))
    return out


def _line_width_words(
    pdf: FPDF, words_line: list[tuple[bool, str]], font_size: int, base_style: str
) -> float:
    """Total width of a line of styled words (Helvetica)."""
    total = 0.0
    for idx, (bold, word) in enumerate(words_line):
        pdf.set_font("Helvetica", style="B" if bold else base_style, size=font_size)
        if idx:
            total += pdf.get_string_width(" ")
        total += pdf.get_string_width(word)
    return total


def _wrap_styled_words(
    pdf: FPDF,
    words: list[tuple[bool, str]],
    max_width: float,
    font_size: int,
    base_style: str = "",
) -> list[list[tuple[bool, str]]]:
    """Word-wrap (bold, word) list into lines that fit max_width."""
    lines_out: list[list[tuple[bool, str]]] = []
    current: list[tuple[bool, str]] = []
    line_width = 0.0

    for bold, word in words:
        pdf.set_font("Helvetica", style="B" if bold else base_style, size=font_size)
        word_w = pdf.get_string_width(word)
        pdf.set_font("Helvetica", style=base_style, size=font_size)
        space_w = pdf.get_string_width(" ")
        need_space = len(current) > 0
        add = word_w + (space_w if need_space else 0)

        if current and line_width + add > max_width:
            lines_out.append(current)
            current = []
            line_width = 0.0
            need_space = False
            add = word_w

        if not current and word_w > max_width:
            # Single oversized token: emit alone (best effort).
            lines_out.append([(bold, word)])
            line_width = 0.0
            continue

        current.append((bold, word))
        line_width += add

    if current:
        lines_out.append(current)
    return lines_out


def _write_styled_line(
    pdf: FPDF,
    words_line: list[tuple[bool, str]],
    line_height: float,
    font_size: int,
    base_style: str,
    align: str,
    inner_width: float,
) -> None:
    """Render one physical line of mixed bold/regular with left or center alignment."""
    total = _line_width_words(pdf, words_line, font_size, base_style)
    if align.upper() == "C":
        x0 = pdf.l_margin + max(0.0, (inner_width - total) / 2)
        pdf.set_x(x0)
    else:
        pdf.set_x(pdf.l_margin)

    for idx, (bold, word) in enumerate(words_line):
        pdf.set_font("Helvetica", style="B" if bold else base_style, size=font_size)
        if idx:
            pdf.write(line_height, " ")
        pdf.write(line_height, word)
    pdf.ln(line_height)


def _render_mixed_markdown_line(
    pdf: FPDF,
    line: str,
    *,
    line_height: float,
    font_size: int,
    base_style: str,
    align: str,
    inner_width: float,
) -> None:
    """One markdown line: inline **bold**, word-wrapped, L or C aligned."""
    segments = _split_bold_segments(line)
    words = _words_from_segments(segments)
    if not words:
        pdf.ln(line_height)
        return
    wrapped = _wrap_styled_words(pdf, words, inner_width, font_size, base_style=base_style)
    for wl in wrapped:
        _write_styled_line(
            pdf, wl, line_height, font_size, base_style, align, inner_width
        )


def _render_heading(
    pdf: FPDF,
    line: str,
    *,
    centered: bool,
    inner_width: float,
) -> None:
    """
    Markdown heading: bold weight and level-based size; left or centered.
    Inline ``**`` is parsed; non-bold segments still use bold (heading style).
    """
    level = min(3, max(1, len(line) - len(line.lstrip("#"))))
    text = line.lstrip("#").strip()
    size = {1: 14, 2: 12, 3: 11}[level]
    line_h = {1: 7.0, 2: 6.5, 3: 6.0}[level]
    pdf.set_font("Helvetica", style="B", size=size)
    # Plain headings: multi_cell (C in header). Inline ``**`` uses write-based flow.
    if "**" not in text:
        pdf.multi_cell(
            0,
            line_h,
            text,
            align="C" if centered else "L",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    else:
        _render_mixed_markdown_line(
            pdf,
            text,
            line_height=line_h,
            font_size=size,
            base_style="B",
            align="C" if centered else "L",
            inner_width=inner_width,
        )
    pdf.set_font("Helvetica", size=10)


def markdown_to_pdf(markdown_text: str, output_name: str | None = None) -> Path:
    """
    Export Markdown-like plain text into a simple ATS-friendly PDF.

    A centered header precedes the main body (see module docstring for split rules).
    Body lines support ``#`` headings and inline ``**bold**``.

    Args:
        markdown_text: CV or cover content in markdown/plain text.
        output_name: Optional filename ending in ``.pdf``.
    Returns:
        Absolute path of the generated PDF.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_name:
        filename = Path(output_name).name
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
    else:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        filename = f"tailored-cv-{stamp}.pdf"

    out_path = OUTPUT_DIR / filename

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)

    cleaned = _ats_clean(markdown_text)
    all_lines = cleaned.splitlines()
    header_lines, body_lines = _split_header_body(all_lines)
    inner_w = pdf.w - pdf.l_margin - pdf.r_margin

    header_name_boost_done = False
    for raw in header_lines:
        line = raw.rstrip()
        if not line:
            pdf.ln(4)
            continue
        if line.startswith("#"):
            _render_heading(pdf, line, centered=True, inner_width=inner_w)
            continue
        fs = 10
        if not header_name_boost_done and _looks_like_name(line):
            fs = 12
            header_name_boost_done = True
        _render_mixed_markdown_line(
            pdf,
            line,
            line_height=6.0,
            font_size=fs,
            base_style="",
            align="C",
            inner_width=inner_w,
        )

    if header_lines and body_lines:
        pdf.ln(2)

    for raw in body_lines:
        line = raw.rstrip()
        if not line:
            pdf.ln(4)
            continue
        if line.startswith("#"):
            _render_heading(pdf, line, centered=False, inner_width=inner_w)
            continue
        _render_mixed_markdown_line(
            pdf,
            line,
            line_height=5.0,
            font_size=10,
            base_style="",
            align="L",
            inner_width=inner_w,
        )

    pdf.output(str(out_path))
    return out_path
