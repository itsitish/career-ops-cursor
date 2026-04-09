"""
Local ATS-style scoring worker: keyword overlap vs target roles, salary heuristics,
and hard rejection when the JD indicates no visa/sponsorship.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Set

# Common English stopwords for keyword extraction (stdlib-only pipeline).
_STOPWORDS: Set[str] = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "as",
    "by", "with", "from", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could", "should", "may",
    "might", "must", "shall", "can", "this", "that", "these", "those", "it", "its",
    "we", "you", "your", "our", "their", "they", "them", "who", "whom", "which",
    "what", "when", "where", "why", "how", "all", "each", "every", "both", "few",
    "more", "most", "other", "some", "such", "no", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "also", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again", "further",
    "then", "once", "here", "there", "any", "if", "about", "against", "while",
    "including", "within", "without", "across", "among", "per", "via", "etc",
    "eg", "ie", "us", "uk", "eu", "role", "roles", "job", "position", "team",
    "company", "work", "working", "experience", "years", "year", "day", "days",
    "time", "full", "part", "based", "opportunity", "looking", "seeking", "join",
    "great", "excellent", "strong", "good", "best", "new", "open", "please",
    "apply", "application", "applications", "candidate", "candidates", "ideal",
    "required", "requirement", "requirements", "preferred", "desirable",
}

# Phrases indicating the employer will not sponsor / no visa support → hard reject.
_NO_SPONSORSHIP_RE = re.compile(
    r"(?:"
    r"no\s+(?:visa|sponsorship|sponsor(?:ship)?\s+available)|"
    r"not\s+(?:able|eligible)\s+to\s+sponsor|"
    r"unable\s+to\s+sponsor|"
    r"does\s+not\s+sponsor|"
    r"will\s+not\s+sponsor|"
    r"cannot\s+sponsor|"
    r"no\s+sponsor(?:ship)?\s+(?:is\s+)?(?:available|offered)|"
    r"sponsorship\s+not\s+(?:available|offered|provided)|"
    r"visa\s+sponsorship\s+not\s+(?:available|offered|provided)|"
    r"we\s+do\s+not\s+(?:offer|provide)\s+(?:visa\s+)?sponsorship|"
    r"right\s+to\s+work\s+in\s+the\s+uk\s+is\s+required|"
    r"must\s+have\s+(?:the\s+)?right\s+to\s+work|"
    r"no\s+relocation|"
    r"uk\s+only\s*\(?\s*no\s+sponsorship"
    r")",
    re.IGNORECASE | re.VERBOSE,
)

# Token pattern: alphanumerics plus common tech chars inside a word boundary.
_TOKEN_RE = re.compile(r"\b[a-z][a-z0-9+#.\-]{2,}\b", re.IGNORECASE)


def _normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return " ".join(text.lower().split())


def _extract_jd_keywords(jd_text: str) -> List[str]:
    """
    Extract candidate keywords from JD text using regex tokens and stopword filtering.
    Preserves order of first occurrence; deduplicates case-insensitively.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for m in _TOKEN_RE.finditer(jd_text.lower()):
        tok = m.group(0)
        if tok in _STOPWORDS or tok.isdigit():
            continue
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _role_vocabulary(target_roles: List[str]) -> Set[str]:
    """Tokenize target role strings into a set for overlap checks."""
    vocab: Set[str] = set()
    for role in target_roles:
        for m in _TOKEN_RE.finditer(role.lower()):
            t = m.group(0)
            if t not in _STOPWORDS:
                vocab.add(t)
    return vocab


def _keyword_overlap(
    jd_keywords: List[str], role_vocab: Set[str]
) -> tuple[List[str], List[str]]:
    """
    Classify JD keywords as matched if they appear in role vocab or as substrings
    of role tokens (handles e.g. 'react' vs 'reactjs').
    """
    matched: List[str] = []
    missing: List[str] = []
    for kw in jd_keywords:
        hit = False
        if kw in role_vocab:
            hit = True
        else:
            for rv in role_vocab:
                if kw in rv or rv in kw:
                    hit = True
                    break
        if hit:
            matched.append(kw)
        else:
            missing.append(kw)
    return matched, missing


def _mentions_no_sponsorship(jd_norm: str) -> bool:
    """True if JD text matches hard-reject sponsorship / visa patterns."""
    return bool(_NO_SPONSORSHIP_RE.search(jd_norm))


def _parse_salary_signals(jd_norm: str) -> tuple[bool, List[int]]:
    """
    Scan JD for salary numbers (GBP implied for UK-style ads).

    Returns:
        found_any: True if any plausible annual figure was parsed
        values: deduplicated annual-like integers (sorted ascending in caller if needed)
    """
    values: List[int] = []

    def _add_amount(n: int) -> None:
        if 15000 <= n <= 500000:
            values.append(n)

    # Ranges like 50-70k / 50k-70k
    for m in re.finditer(
        r"\b(\d{2,3})\s*k?\s*[-–]\s*(\d{2,3})\s*k\b",
        jd_norm,
        re.IGNORECASE,
    ):
        for g in (m.group(1), m.group(2)):
            _add_amount(int(g) * 1000)

    # £60k, £60,000, 55k, up to 70k (single figure)
    for m in re.finditer(
        r"(?:£\s*)?(\d{1,3}(?:,\d{3})+|\d{2,6})\s*k\b",
        jd_norm,
        re.IGNORECASE,
    ):
        digits = m.group(1).replace(",", "")
        if not digits.isdigit():
            continue
        n = int(digits)
        if n < 1000:
            n *= 1000
        _add_amount(n)

    # £60000 / 60000 (no k)
    for m in re.finditer(r"£\s*(\d{5,6})\b", jd_norm):
        _add_amount(int(m.group(1)))

    for m in re.finditer(r"\b(\d{5,6})\b", jd_norm):
        _add_amount(int(m.group(1)))

    if not values:
        return False, []

    return True, list(dict.fromkeys(values))


def _salary_assessment(required_gbp: int, jd_norm: str) -> tuple[int, List[str]]:
    """
    Adjust score delta and reasons based on parsed salary vs required_gbp.

    Returns:
        score_delta: negative if penalized, 0 if neutral/pass
        reasons: human-readable strings
    """
    reasons: List[str] = []
    found, values = _parse_salary_signals(jd_norm)

    if not found or not values:
        return 0, reasons

    max_v = max(values)

    # Pass if any stated figure or band top meets/exceeds requirement
    if max_v >= required_gbp:
        return 0, reasons

    gap = required_gbp - max_v
    reasons.append(
        f"Stated compensation appears below required £{required_gbp:,} "
        f"(max parsed ~£{max_v:,})."
    )
    penalty = min(35, 10 + gap // 5000)
    return -penalty, reasons


class AtsScoringWorker:
    """
    Cursor-triggered worker: scores a JD against target role tokens and policy rules.
    """

    worker_id: str = "ats_scoring_worker"

    def can_handle(self, task_type: str) -> bool:
        """Return True if this worker supports the given task type."""
        return task_type == "score_jd"

    def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run ATS-style scoring for task type ``score_jd``.

        Expected ``task`` shape::
            {
                "task_type": "score_jd",
                "payload": {
                    "jd_text": str,
                    "target_roles": list[str],
                    "required_salary_gbp": int (optional, default 60000),
                },
            }

        Also accepts ``type`` instead of ``task_type`` and payload merged at top level.
        """
        payload = task.get("payload")
        if not isinstance(payload, dict):
            payload = {
                k: v
                for k, v in task.items()
                if k not in ("task_type", "type", "payload")
            }

        jd_text = payload.get("jd_text") or ""
        if not isinstance(jd_text, str):
            jd_text = str(jd_text)

        target_roles = payload.get("target_roles") or []
        if not isinstance(target_roles, list):
            target_roles = [str(target_roles)]
        else:
            target_roles = [str(r) for r in target_roles]

        required_salary_gbp = payload.get("required_salary_gbp", 60000)
        try:
            required_salary_gbp = int(required_salary_gbp)
        except (TypeError, ValueError):
            required_salary_gbp = 60000

        jd_norm = _normalize_text(jd_text)
        rejection_reasons: List[str] = []

        jd_keywords = _extract_jd_keywords(jd_text)
        role_vocab = _role_vocabulary(target_roles)
        matched_keywords, missing_keywords = _keyword_overlap(jd_keywords, role_vocab)

        if _mentions_no_sponsorship(jd_norm):
            rejection_reasons.append(
                "JD indicates no visa/sponsorship or right-to-work restrictions incompatible "
                "with sponsorship needs — hard reject."
            )
            return {
                "ats_score": 18,
                "missing_keywords": missing_keywords,
                "matched_keywords": matched_keywords,
                "rejection_reasons": rejection_reasons,
            }

        if not jd_keywords:
            base = 40
        else:
            ratio = len(matched_keywords) / len(jd_keywords)
            base = int(round(35 + 55 * ratio))

        sal_delta, sal_reasons = _salary_assessment(required_salary_gbp, jd_norm)
        rejection_reasons.extend(sal_reasons)

        score = max(0, min(100, base + sal_delta))

        if len(target_roles) == 0 and jd_keywords:
            rejection_reasons.append(
                "No target_roles provided; keyword match score may be unreliable."
            )
            score = max(0, score - 15)

        return {
            "ats_score": int(score),
            "missing_keywords": missing_keywords,
            "matched_keywords": matched_keywords,
            "rejection_reasons": rejection_reasons,
        }
