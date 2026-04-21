"""
Local worker that builds a deterministic Markdown prompt for Cursor to tailor a CV
and cover letter from a master CV plus knowledge-base highlights.

Also emits ``tailored_cv_markdown`` and ``tailored_cover_markdown`` using local,
deterministic heuristics (no external API calls).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from app.services.prompt_analysis import (
    extract_must_have_snippets,
    infer_locale_instruction,
    keyword_evidence_table_md,
    top_jd_keywords,
)

# --- shared helpers -----------------------------------------------------------

_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "to",
        "of",
        "in",
        "for",
        "with",
        "on",
        "at",
        "by",
        "as",
        "is",
        "are",
        "be",
        "this",
        "that",
        "will",
        "you",
        "we",
        "our",
        "your",
        "from",
        "have",
        "has",
        "been",
        "any",
        "all",
        "can",
        "may",
        "into",
        "their",
        "they",
        "them",
        "who",
        "what",
        "which",
        "about",
        "such",
        "via",
        "per",
    }
)


def _bullet_list(items: List[str], prefix: str = "- ") -> str:
    """Render a list of strings as Markdown bullet lines."""
    lines: List[str] = []
    for item in items:
        s = str(item).strip()
        if s:
            lines.append(f"{prefix}{s}")
    return "\n".join(lines) if lines else "_None provided._"


def _jd_keyword_tokens(jd_text: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from the JD, minus short/stop words."""
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9+/\-]*", jd_text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _bullet_jd_score(line: str, jd_kw: set[str]) -> int:
    """Count JD keyword hits in a line (word-boundary aware)."""
    low = line.lower()
    return sum(1 for w in jd_kw if re.search(rf"\b{re.escape(w)}\b", low))


def _word_count(text: str) -> int:
    """Count words for cover-letter length bounds."""
    return len(re.findall(r"\b\w+\b", text))


def _is_bullet_line(line: str) -> bool:
    """True when a line starts with a Markdown-style bullet marker."""
    return bool(re.match(r"^\s*[-*•]\s+\S", line))


def _section_starts(line: str) -> bool:
    """True when a line begins a logical CV section (after preamble)."""
    if re.match(r"^\s*##\s+\S", line):
        return True
    s = line.strip()
    return bool(
        re.match(
            r"(?i)^(profile|summary|objective|experience|work experience|employment"
            r"|employment history|education|skills|projects|certifications)\s*:?\s*$",
            s,
        )
    )


def _split_preamble_and_sections(lines: List[str]) -> Tuple[List[str], List[Tuple[str, List[str]]]]:
    """
    Split CV lines into preamble (identity/contact) and (header, body) sections.

    Preamble runs until the first ``##`` heading or known section keyword line.
    """
    i = 0
    n = len(lines)
    preamble: List[str] = []
    while i < n and not _section_starts(lines[i]):
        preamble.append(lines[i])
        i += 1
    sections: List[Tuple[str, List[str]]] = []
    while i < n:
        header = lines[i]
        i += 1
        body: List[str] = []
        while i < n and not _section_starts(lines[i]):
            body.append(lines[i])
            i += 1
        sections.append((header, body))
    return preamble, sections


def _is_experience_header(header: str) -> bool:
    """Return True for section headings that represent work-history content."""
    h = header.lower()
    return any(
        k in h
        for k in (
            "experience",
            "employment",
            "work experience",
            "work history",
        )
    )


def _reorder_bullets_in_body(body: List[str], jd_kw: set[str]) -> List[str]:
    """Within a section body, sort contiguous bullet blocks by JD keyword score."""
    out: List[str] = []
    i = 0
    while i < len(body):
        line = body[i]
        if _is_bullet_line(line):
            bullets: List[str] = []
            j = i
            while j < len(body) and _is_bullet_line(body[j]):
                bullets.append(body[j])
                j += 1
            bullets.sort(
                key=lambda b: (_bullet_jd_score(b, jd_kw), b),
                reverse=True,
            )
            out.extend(bullets)
            i = j
        else:
            out.append(line)
            i += 1
    return out


def _theme_phrases_from_master(master_lower: str) -> List[str]:
    """
    Derive JD-adjacent theme labels only when the master CV actually mentions them.

    Covers software engineering, MLOps, and platform reliability wording.
    """
    themes: List[str] = []
    if re.search(
        r"\b(mlops|machine learning|\bml\b|model serving|pytorch|tensorflow|keras|llm|nlp)\b",
        master_lower,
    ):
        themes.append("MLOps and machine learning delivery")
    if re.search(
        r"\b(sre|reliability|on-?call|incident|observability|monitoring|kubernetes|k8s|docker|terraform|platform|infrastructure|devops|ci/cd|pipeline)\b",
        master_lower,
    ):
        themes.append("platform reliability and infrastructure")
    if re.search(
        r"\b(software|developer|engineer|engineering|backend|frontend|full[- ]stack|api|microservice|distributed)\b",
        master_lower,
    ):
        themes.append("software engineering")
    return themes


def _extract_sign_name(preamble: List[str]) -> str:
    """First non-empty line, stripped of leading Markdown heading markers."""
    for line in preamble:
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^#+\s*", "", s)
        return s
    return "Candidate"


def _top_fact_clips(master_cv: str, jd_kw: set[str], max_clips: int = 4) -> List[str]:
    """Short clips from high-scoring experience bullets (facts only, no invention)."""
    clips: List[str] = []
    for line in master_cv.splitlines():
        if not _is_bullet_line(line):
            continue
        raw = re.sub(r"^\s*[-*•]\s+", "", line).strip()
        if len(raw) < 8:
            continue
        score = _bullet_jd_score(line, jd_kw)
        clips.append((score, raw))
    clips.sort(key=lambda x: (-x[0], x[1]))
    seen = set()
    out: List[str] = []
    for _, raw in clips:
        key = raw.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(raw[:220] + ("…" if len(raw) > 220 else ""))
        if len(out) >= max_clips:
            break
    return out


def _build_tailored_profile_summary(
    master_cv: str,
    jd_kw: set[str],
    preamble: List[str],
) -> str:
    """
    Short profile tuned to JD themes using only master-CV evidence.

    Uses theme phrases only when the master CV already supports them.
    """
    master_lower = master_cv.lower()
    themes = _theme_phrases_from_master(master_lower)
    clips = _top_fact_clips(master_cv, jd_kw, max_clips=4)
    sign = _extract_sign_name(preamble)

    theme_bit = ""
    if themes:
        theme_bit = "Focus areas include " + ", ".join(themes) + ". "

    if clips:
        fact_bit = "Representative experience includes: " + "; ".join(clips) + "."
    else:
        # Fall back to first substantive non-bullet lines from master (still factual).
        fallback: List[str] = []
        for line in master_cv.splitlines():
            s = line.strip()
            if not s or _is_bullet_line(line) or s.startswith("#"):
                continue
            if len(s) > 400:
                s = s[:400] + "…"
            fallback.append(s)
            if len(fallback) >= 2:
                break
        fact_bit = " ".join(fallback) if fallback else "See the Experience section for detailed roles and outcomes."

    return f"**{sign}** — {theme_bit}{fact_bit}"


def _merge_profile_section(
    sections: List[Tuple[str, List[str]]],
    profile_md: str,
) -> List[Tuple[str, List[str]]]:
    """Insert or replace Profile/Summary body with ``profile_md``; keeps one profile block."""
    profile_hdr = re.compile(r"(?i)^\s*#{1,3}\s*(profile|summary|objective)\b")
    new_sections: List[Tuple[str, List[str]]] = []
    inserted = False
    for hdr, body in sections:
        if profile_hdr.search(hdr):
            if not inserted:
                new_sections.append((hdr, [profile_md]))
                inserted = True
            # Drop duplicate profile sections from master.
            continue
        new_sections.append((hdr, body))
    if not inserted:
        new_sections.insert(0, ("## Profile", [profile_md]))
    return new_sections


def _build_tailored_cv_markdown(master_cv: str, jd_text: str) -> str:
    """
    Parse master CV lines, preserve preamble and headers, reorder experience bullets
    by JD keyword overlap, and inject a concise tailored profile.
    """
    lines = master_cv.splitlines()
    preamble, sections = _split_preamble_and_sections(lines)
    jd_kw = _jd_keyword_tokens(jd_text)
    profile_text = _build_tailored_profile_summary(master_cv, jd_kw, preamble)

    merged = _merge_profile_section(sections, profile_text)
    out_lines: List[str] = []
    out_lines.extend(preamble)
    if preamble and merged and preamble[-1].strip():
        out_lines.append("")

    for hdr, body in merged:
        out_lines.append(hdr)
        if _is_experience_header(hdr):
            body = _reorder_bullets_in_body(body, jd_kw)
        out_lines.extend(body)
        out_lines.append("")

    return "\n".join(out_lines).rstrip() + "\n"


def _split_sentences(text: str) -> List[str]:
    """Split on sentence boundaries; keeps deterministic order."""
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 15]


def _sentence_jd_score(sentence: str, jd_kw: set[str]) -> int:
    """Sentence-level alias of bullet scoring for cover-letter sentence ranking."""
    return _bullet_jd_score(sentence, jd_kw)


def _master_word_chunks(
    master_cv: str,
    chunk_words: int = 40,
    step: int = 22,
) -> List[str]:
    """
    Overlapping word windows from the CV body for cover padding (no new facts).

    Skips Markdown heading lines; joins remaining lines so wording stays verbatim
    to the master file. Sliding ``step`` < ``chunk_words`` yields multiple spans
    from short CVs so total length targets remain reachable.
    """
    lines: List[str] = []
    for line in master_cv.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if _is_bullet_line(line):
            s = re.sub(r"^\s*[-*•]\s+", "", line).strip()
        lines.append(s)
    blob = " ".join(lines)
    words = blob.split()
    out: List[str] = []
    if len(words) < 8:
        return out
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_words]).strip()
        if _word_count(chunk) >= 10:
            out.append(chunk)
        i += step
        if i >= len(words) and len(out) == 0:
            break
    return out


def _build_tailored_cover_markdown(
    jd_text: str,
    master_cv: str,
    kb_highlights: List[str],
    sign_name: str,
) -> str:
    """
    Concise cover letter (220–320 words) from JD-aligned sentences in highlights + CV.

    No fabricated employers, dates, or metrics — only stitched source text.
    """
    jd_kw = _jd_keyword_tokens(jd_text)
    candidates: List[Tuple[int, str]] = []

    # Rank short factual snippets first so the cover letter starts from the most
    # JD-aligned evidence before falling back to verbatim padding from the master CV.
    for h in kb_highlights:
        for sent in _split_sentences(h):
            candidates.append((_sentence_jd_score(sent, jd_kw), sent))

    for line in master_cv.splitlines():
        if _is_bullet_line(line):
            sent = re.sub(r"^\s*[-*•]\s+", "", line).strip()
            if len(sent) > 20:
                candidates.append((_sentence_jd_score(sent, jd_kw), sent))

    candidates.sort(key=lambda x: (-x[0], x[1]))
    ordered_sents: List[str] = []
    seen: set[str] = set()
    for _, sent in candidates:
        key = re.sub(r"\s+", " ", sent).casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered_sents.append(sent)

    # Deterministic padding pool: verbatim CV windows (JD score 0) after ranked sentences.
    for chunk in _master_word_chunks(master_cv):
        key = re.sub(r"\s+", " ", chunk).casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered_sents.append(chunk)

    opener = (
        "Dear Hiring Manager,\n\n"
        "I am writing regarding the opportunity described in your posting. "
        "The following points summarise experience that aligns with your requirements, "
        "drawn directly from my CV and supporting notes.\n\n"
    )
    closing = (
        "\n\nI would welcome a conversation about how this background can support your team.\n\n"
        f"Sincerely,\n{sign_name}\n"
    )

    low_w, high_w = 220, 320

    def total_wc(body: str) -> int:
        return _word_count(opener + body.strip() + closing)

    body_sents: List[str] = []
    for sent in ordered_sents:
        trial = " ".join(body_sents + [sent])
        if total_wc(trial) > high_w and body_sents:
            break
        body_sents.append(sent)
        if total_wc(" ".join(body_sents)) >= low_w:
            break

    if total_wc(" ".join(body_sents)) < low_w:
        for sent in ordered_sents:
            if sent in body_sents:
                continue
            trial = " ".join(body_sents + [sent])
            if total_wc(trial) > high_w:
                continue
            body_sents.append(sent)
            if total_wc(" ".join(body_sents)) >= low_w:
                break

    # Very short CVs: append a verbatim CV blob until we approach ``low_w`` without
    # inventing any filler content outside the user's materials.
    blob_pad = " ".join(
        s.strip()
        for s in master_cv.splitlines()
        if s.strip() and not s.strip().startswith("#")
    ).strip()
    while blob_pad and total_wc(" ".join(body_sents)) < low_w:
        trial = " ".join(body_sents + [blob_pad])
        if total_wc(trial) > high_w:
            break
        body_sents.append(blob_pad)
        if total_wc(" ".join(body_sents)) >= low_w:
            break

    body = " ".join(body_sents)
    draft = opener + body + closing
    if _word_count(draft) > high_w:
        words = draft.split()[:high_w]
        draft = " ".join(words).rstrip(",;:")
        if draft and draft[-1] not in ".!?":
            draft += "."
    return draft


class CvTailorWorker:
    """
    Produces ``prompt_markdown``, ``checklist``, and locally tailored Markdown documents.

    No external API calls; same inputs → same outputs.
    """

    worker_id: str = "cv_tailor_worker"

    def can_handle(self, task_type: str) -> bool:
        """Return True if this worker supports the given task type."""
        return task_type == "tailor_cv_prompt"

    def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a paste-ready Cursor prompt for CV + cover letter tailoring.

        Expected ``task`` shape::
            {
                "task_type": "tailor_cv_prompt",
                "payload": {
                    "jd_text": str,
                    "master_cv_markdown": str,
                    "kb_highlights": list[str],
                    "cover_requested": bool (optional),
                    "prompt_only": bool (optional),
                    "locale_hint": str (optional, e.g. en-GB),
                },
            }

        Top-level keys are also accepted if ``payload`` is omitted.

        Returns:
            dict with ``prompt_markdown``, ``checklist``, ``tailored_cv_markdown``,
            and ``tailored_cover_markdown``.
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

        master_cv = payload.get("master_cv_markdown") or ""
        if not isinstance(master_cv, str):
            master_cv = str(master_cv)

        kb = payload.get("kb_highlights") or []
        if not isinstance(kb, list):
            kb = [str(kb)]
        kb_lines = [str(x).strip() for x in kb if str(x).strip()]

        cover_requested = bool(payload.get("cover_requested", False))
        prompt_only = bool(payload.get("prompt_only", True))

        locale_hint = str(payload.get("locale_hint") or "en-GB").strip() or "en-GB"

        prompt_markdown = self._build_prompt_markdown(
            jd_text=jd_text.strip(),
            master_cv_markdown=master_cv.strip(),
            kb_highlights=kb_lines,
            cover_requested=cover_requested,
            locale_hint=locale_hint,
        )
        checklist = self._build_checklist(
            jd_text=jd_text.strip(),
            kb_highlights=kb_lines,
            cover_requested=cover_requested,
        )

        preamble, _ = _split_preamble_and_sections(master_cv.splitlines())
        sign = _extract_sign_name(preamble)

        if prompt_only:
            tailored_cv = ""
            tailored_cover = ""
        else:
            tailored_cv = _build_tailored_cv_markdown(master_cv.strip(), jd_text.strip())
            if cover_requested:
                tailored_cover = _build_tailored_cover_markdown(
                    jd_text.strip(),
                    master_cv.strip(),
                    kb_lines,
                    sign_name=sign,
                )
            else:
                tailored_cover = ""

        return {
            "prompt_markdown": prompt_markdown,
            "checklist": checklist,
            "tailored_cv_markdown": tailored_cv,
            "tailored_cover_markdown": tailored_cover,
        }

    def _build_prompt_markdown(
        self,
        jd_text: str,
        master_cv_markdown: str,
        kb_highlights: List[str],
        *,
        cover_requested: bool = False,
        locale_hint: str = "en-GB",
    ) -> str:
        """
        Assemble the full Markdown prompt: JD analysis, keyword evidence, tasks, constraints.

        Designed for Cursor chat to refactor and reword the CV using only supplied facts.
        """
        kb_block = _bullet_list(kb_highlights)
        cv_block = master_cv_markdown if master_cv_markdown else "_Master CV empty — paste your CV here._"
        jd_block = jd_text if jd_text else "_Job description empty — paste the JD here._"

        must_lines = extract_must_have_snippets(jd_text) if jd_text.strip() else []
        must_block = _bullet_list(must_lines) if must_lines else "_No lines extracted — rely on full JD above._"

        jd_kw = top_jd_keywords(jd_text, limit=28) if jd_text.strip() else []
        evidence_table = keyword_evidence_table_md(
            jd_kw, master_cv_markdown, kb_highlights, max_rows=18
        )
        locale_line = infer_locale_instruction(jd_text, locale_hint)

        tasks_block = (
            "1. **Tailored CV (Markdown)** — Refactor for clarity and ATS fit:\n"
            "   - First, make a **keep / condense / remove** judgement for each role, project, and major bullet based "
            "on the JD. Do **not** preserve the master CV structure by default.\n"
            "   - Reorder and **materially rewrite** experience bullets so order and wording track the JD’s language "
            "and priority (strongest matches first; mirror phrasing where truthful). Avoid cosmetic edits that keep the "
            "same bullet substance and ordering.\n"
            "   - Reword the **headline / profile / summary** (if present) so it speaks directly to this role — "
            "using only facts from the master CV and KB.\n"
            "   - For highly relevant roles, keep more detail and move the most JD-aligned bullets to the top.\n"
            "   - For partially relevant roles, keep only the bullets that support this JD and compress the rest.\n"
            "   - For weakly relevant or irrelevant roles / projects, reduce them to 0-2 short bullets, or remove "
            "them entirely if chronology still reads cleanly.\n"
            "   - **Omit or heavily condense** tools, projects, bullets, and older experience that do not help this "
            "application; in the **change log**, note honestly what was removed or shortened and why (no fabricated "
            "gaps or implied employment holes).\n"
            "   - Reorder sections and bullets so the **first screen** reflects the JD’s strongest must-haves.\n"
            "   - Rephrase bullets for impact (strong verbs, quantified facts **only** where already in the master).\n"
            "   - Mirror important JD keywords **where truthful**; use the evidence table — do not claim **none** rows.\n"
            "   - Avoid repeating the same phrases across the headline, summary, Core Skills, and experience bullets; "
            "vary wording while keeping the meaning accurate.\n"
            "   - In **Core Skills**, format each category label in bold, e.g. `**ML & Statistical Methods:**`.\n"
            "   - Throughout the CV, bold important JD-aligned keywords, tools, and capability phrases for scanability.\n"
            "   - Keep length comparable to the master unless a shorter, more targeted CV clearly improves fit.\n"
        )
        n = 2
        if cover_requested:
            tasks_block += (
                f"{n}. **Cover letter (Markdown)** — 250–350 words: specific opening, 2–3 paragraphs "
                "with evidence from master/KB only, concise closing.\n"
            )
            n += 1
        tasks_block += (
            f"{n}. **Change log** — Markdown bullet list: what changed vs the master and **why** "
            "(JD alignment). Call out **gaps** where the JD asks for something not in the materials.\n"
        )

        return (
            "## Role\n"
            "You are refining a job application in **Cursor**. Use **only** facts present in the "
            "**Master CV** and **Knowledge-base highlights**. Do not invent employers, dates, metrics, "
            "degrees, certifications, or tools. If a JD requirement is not evidenced, state it in the "
            "change log as a gap — do not imply you have it.\n\n"
            "## Job description (verbatim)\n"
            f"{jd_block}\n\n"
            "## JD signals (deterministic extract)\n"
            "### Lines likely tied to requirements / responsibilities\n"
            f"{must_block}\n\n"
            "### Keyword ↔ evidence (master CV + KB)\n"
            "Use this to prioritize wording and to flag honest gaps.\n\n"
            f"{evidence_table}\n\n"
            "## Master CV (Markdown)\n"
            f"{cv_block}\n\n"
            "## Knowledge-base highlights (trusted facts / themes)\n"
            f"{kb_block}\n\n"
            "## Rewriting guidance\n"
            "- Prefer **British English** for UK JDs and **US English** for US JDs when unambiguous from the JD.\n"
            "- **ATS:** include role-relevant keywords naturally in headings and first bullets where they match truth.\n"
            "- **Selection pressure:** treat the JD as the ranking function. If a bullet does not help this application, "
            "rewrite it sharply, compress it, or remove it.\n"
            "- **Experience pruning:** it is acceptable to shorten or drop low-value bullets and less relevant projects; "
            "do not keep content just because it exists in the master CV.\n"
            "- **Bullet rewriting:** prefer rewriting bullets around outcomes, scope, and role-relevant skills rather "
            "than lightly paraphrasing the original sentence.\n"
            "- **Repetition control:** do not reuse the same JD phrase or marketing line multiple times unless it is "
            "genuinely necessary; spread related concepts across varied, natural wording.\n"
            "- **Failure mode to avoid:** do not return a near-copy of the master CV. The final draft should show real "
            "prioritization, rewritten bullets, and visible pruning where the JD makes that appropriate.\n"
            "- **Markdown:** use `**bold**` deliberately for Core Skills labels and important JD-aligned keywords "
            "throughout the CV; keep bolding to short phrases, not whole bullets or paragraphs.\n"
            "- **No fabrication:** paraphrase and compress; never add employers, tools, or numbers not in the source.\n\n"
            "## Tasks\n"
            f"{tasks_block}\n"
            "## Constraints\n"
            "- No fabricated achievements, numbers, or credentials.\n"
            "- If the JD requires something not evidenced in the master CV or highlights, "
            "document it only in the **change log** as a gap.\n"
            "- Do not preserve every original bullet or project by default; remove or compress low-value content when "
            "it improves JD fit.\n"
        )

    def _build_checklist(
        self,
        jd_text: str,
        kb_highlights: List[str],
        *,
        cover_requested: bool = True,
    ) -> List[str]:
        """Return a fixed, human-oriented review checklist (deterministic)."""
        has_jd = bool(jd_text.strip())
        has_kb = bool(kb_highlights)

        items: List[str] = [
            "Confirm every stated tool, title, employer, and date appears in the master CV or KB highlights.",
            "Verify JD must-have requirements are either clearly evidenced or explicitly flagged as gaps.",
            "Check for accidental duplication or inflated seniority compared with the master CV.",
            "Check that the experience bullets were materially rewritten for the JD, not just lightly paraphrased.",
            "Check that weakly relevant bullets, projects, or older experience were shortened or removed where appropriate.",
        ]
        if cover_requested:
            items.extend(
                [
                    "Scan for spelling, grammar, and consistent tense in CV and cover letter.",
                    "Ensure the cover letter does not repeat the CV verbatim; it should add narrative context.",
                ]
            )
        else:
            items.append(
                "Scan for spelling, grammar, and consistent tense in the CV.",
            )
        if not has_jd:
            items.insert(0, "Paste the full job description — checklist assumes JD was empty in the prompt.")
        if not has_kb:
            items.insert(0, "Add KB highlights if you have verified facts/themes not fully captured in the master CV.")

        return items
