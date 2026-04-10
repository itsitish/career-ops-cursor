"""
Deterministic JD analysis blocks for Cursor tailor prompts (no LLM calls).

Extracts must-have style lines, top keywords, and a simple evidence map vs master CV + KB.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple

# Lines likely listing requirements (heuristic).
_MUST_LINE_RE = re.compile(
    r"(?i)(must-have|must have|required|minimum\s+\d|qualifications?|"
    r"you will|you\'ll|responsibilit|experience with|proficient in|"
    r"hands-on|knowledge of|familiarity with|strong\s+\w+\s+skills?)",
)


def extract_must_have_snippets(jd_text: str, max_lines: int = 24) -> List[str]:
    """
    Pull JD lines that look like requirements or responsibilities.

    Conservative: prefers non-empty lines matching heuristic patterns or bullet-like lines.
    """
    lines = jd_text.splitlines()
    out: List[str] = []
    for line in lines:
        s = line.strip()
        if len(s) < 12:
            continue
        if _MUST_LINE_RE.search(s) or re.match(r"^[-*•]\s+\S", s):
            out.append(s[:500] + ("…" if len(s) > 500 else ""))
        if len(out) >= max_lines:
            break
    if len(out) < 5:
        # Broader fallback: first substantive lines from major sections
        for line in lines:
            s = line.strip()
            if len(s) < 20:
                continue
            if s in out:
                continue
            out.append(s[:500] + ("…" if len(s) > 500 else ""))
            if len(out) >= max_lines:
                break
    return out[:max_lines]


_STOPWORDS = frozenset(
    {
        "the", "a", "an", "and", "or", "to", "of", "in", "for", "with", "on", "at", "by",
        "is", "are", "be", "this", "that", "will", "you", "we", "our", "your", "from",
        "have", "has", "any", "all", "can", "may", "as", "an", "role", "job", "team",
        "work", "working", "opportunity", "looking", "seeking",
    }
)


def top_jd_keywords(jd_text: str, limit: int = 28) -> List[str]:
    """Ordered unique tokens from JD (length > 2), excluding common stopwords."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+#.\-]{2,}", jd_text.lower())
    seen: Set[str] = set()
    out: List[str] = []
    for w in words:
        if w in _STOPWORDS or w.isdigit():
            continue
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= limit:
            break
    return out


def _evidence_for_keyword(kw: str, master_cv: str, kb_text: str) -> Tuple[str, str]:
    """
    Return (strength, one_line_note).

    strength: strong | weak | none
    """
    low = kw.lower()
    mlow = master_cv.lower()
    blow = kb_text.lower()
    if re.search(rf"\b{re.escape(low)}\b", mlow):
        return "strong", "Appears in master CV."
    if re.search(rf"\b{re.escape(low)}\b", blow):
        return "weak", "Mentioned in KB highlights only."
    # substring for compound tech names
    if low in mlow.replace("-", ""):
        return "strong", "Related term in master CV."
    return "none", "Not found in master CV or KB — list as gap if JD-critical."


def keyword_evidence_table_md(
    jd_keywords: List[str],
    master_cv: str,
    kb_highlights: List[str],
    max_rows: int = 18,
) -> str:
    """Markdown table: Keyword | Evidence | Note."""
    kb_blob = "\n".join(kb_highlights)
    rows: List[str] = []
    rows.append("| JD keyword / theme | Evidence in materials | Note |")
    rows.append("| --- | --- | --- |")
    for kw in jd_keywords[:max_rows]:
        strength, note = _evidence_for_keyword(kw, master_cv, kb_blob)
        rows.append(f"| `{kw}` | {strength} | {note} |")
    return "\n".join(rows)


def infer_locale_instruction(jd_text: str, locale_hint: str) -> str:
    """Short line telling the model which spelling to prefer."""
    jd_low = jd_text.lower()
    uk_signals = ("£", "gbp", "united kingdom", " uk ", "london", "leeds", "manchester")
    us_signals = ("$", "usd", "united states", "remote us", "sf ", "ny ")
    if any(s in jd_low for s in uk_signals):
        return "Use British English spelling and date formats."
    if any(s in jd_low for s in us_signals):
        return "Use US English spelling unless the CV is clearly UK-oriented."
    if locale_hint.lower().startswith("en-gb"):
        return "Default to British English (profile locale en-GB)."
    if locale_hint.lower().startswith("en-us"):
        return "Default to US English (profile locale en-US)."
    return "Match the JD's locale/spelling where obvious; otherwise keep the master CV's variety."
