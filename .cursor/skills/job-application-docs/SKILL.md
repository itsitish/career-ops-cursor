---
name: job-application-docs
description: >-
  Tailors CV and cover letters to job descriptions while honoring user constraints.
  Use when the user asks for CV, résumé, resume, cover letter, job application
  materials, or JD alignment.
---

# Job application documents

## When this skill applies

Use this workflow whenever the user wants application materials tailored to a **job description (JD)** or role brief. 

## Inputs to require from the user

1. **Job description** — full text or link plus pasted content (links alone are not enough if the agent cannot fetch them).
2. **Constraints** — length limits, tone (formal / direct), region or language variant, ATS or keyword preferences, format (Markdown vs plain text), and anything to **avoid** (e.g. salary history, certain employers).
3. **Deliverables** — CV only, cover letter only, or both.

If the JD or constraints are missing, ask for them before producing final copy.

## Source of truth (no fabrication)

- **Facts** (employers, titles, dates, education, certifications, metrics) must come only from prompt
- Do **not** invent employers, dates, credentials, or numbers. If something needed for a strong match is missing, **state the gap** and suggest bullet wording the user can verify, or ask a targeted question.

## Tailoring rules

- Mirror **honest** overlap with the JD: reuse terminology the user’s experience actually supports.
- **Reorder and emphasize** bullets to surface the most relevant wins for this role; do not add new achievements.
- One master truth: tailored versions are **spins** of the same facts, not alternate histories.

## Output format

Use clearly separated blocks so the user can copy each artifact:

```text
--- CV (tailored) ---
[CV body per user’s requested format]

--- Cover letter ---
[Letter body; default ~250–400 words unless the user specifies otherwise]
```

If only one deliverable was requested, omit the other section and label accordingly.
Zs
## Using this skill from another chat or agent

This skill lives **in this repository** at `.cursor/skills/job-application-docs/`. Other clones of the repo get the same files under `.cursor/skills/`.

If the agent does not load it automatically, the user can `@`-mention `SKILL.md` or say: follow `.cursor/skills/job-application-docs/SKILL.md` 

## Sharing across machines

- **Same repo, new machine:** `git pull` (commit `.cursor/skills/job-application-docs/` if you want it versioned).
- **Copy manually:** copy the folder `job-application-docs` into another project’s `.cursor/skills/` only if you intend to use it there.
