"""
PDF export helper for tailored CV/Cover markdown text.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import textwrap

from fpdf import FPDF


OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output" / "resumes"


def markdown_to_pdf(markdown_text: str, output_name: str | None = None) -> Path:
    """
    Export Markdown-like plain text into a simple ATS-friendly PDF.

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

    # Keep characters ATS-safe by replacing common non-ASCII punctuation.
    cleaned = (
        markdown_text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )

    for raw_line in cleaned.splitlines():
        line = raw_line.rstrip()
        if not line:
            pdf.ln(4)
            continue
        if line.startswith("#"):
            level = min(3, max(1, len(line) - len(line.lstrip("#"))))
            text = line.lstrip("#").strip()
            size = {1: 14, 2: 12, 3: 11}[level]
            pdf.set_font("Helvetica", style="B", size=size)
            for wrapped in textwrap.wrap(text, width=85) or [" "]:
                pdf.cell(0, 6, wrapped, new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=10)
            continue
        for wrapped in textwrap.wrap(line, width=100) or [" "]:
            pdf.cell(0, 5, wrapped, new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(out_path))
    return out_path
