# Career Ops (Cursor)

## What this is

- **Tailoring default** — With `CURSOR_USE_LLM=0` (or unset), CV/cover output is **local and deterministic** (same inputs → same markdown). No LLM required.
- **Cursor API mode (single pinned model)** — Enable `CURSOR_USE_CLOUD_AGENT=1` and set `CURSOR_API_KEY`, `CURSOR_API_BASE=https://api.cursor.com`, `CURSOR_SOURCE_REPOSITORY`, and `CURSOR_AGENT_MODEL` (single pinned model id from `GET /v0/models`, e.g. `claude-4.6-opus-high-thinking` if available). The app launches Cursor Cloud Agents (`/v0/agents`) for tailor requests and returns `provider_used=cursor-cloud-agent` when successful.
- **Optional OpenAI-compatible mode** — If Cloud Agent mode is off, `CURSOR_USE_LLM=1` + `CURSOR_OPENAI_BASE_URL` uses OpenAI-compatible `/chat/completions` behavior.
- **Fallback** — If provider calls fail, the app falls back to local deterministic tailoring.
- **Scraping** — uses `requests` / BeautifulSoup (no paid scrape APIs). You can still use **Cursor-in-the-loop** with the generated prompt markdown.
- **PDF output** — export tailored markdown via `POST /api/cv/export-pdf` to `output/resumes/`.
- **Salary**: listings are filtered at scrape time when a GBP salary parses below **£60,000** (`min_salary_gbp` in the scheduler).
- **Sponsorship**: the ATS worker **hard-rejects** job descriptions that clearly state no visa/sponsorship (see `app/services/ats_worker.py`).
- **Master CV auto-use** — `tailor-prompt` uses your latest uploaded master CV when manual CV text is left empty.

## Dashboard notes (concise)

- **Copy/paste workflow** — Optional **cover** in the tailor prompt defaults **off**; turn it on when you want cover instructions and JSON to include a cover letter.
- **Tailor prompt** — Prompt generation **deduplicates** KB rows and drops **overlap with the master CV** so highlights stay additive.
- **Add KB text** — `POST /api/kb/add-text`: **Content** is the snippet stored; **Entry type** is a short label (default `note`, e.g. `upload` for files) used when listing/filtering KB rows.
- **Score JD** — Removed from the dashboard UI; scoring is still available via **`POST /api/jobs/score`** (JSON: `jd_text`, `target_roles`, `required_salary_gbp`).

## Where to put your files

| Asset | Suggested path |
|--------|----------------|
| Master CV (markdown or text you paste into tailor prompts) | `data/master_cv.md` (create if needed; mounted in Docker) |
| Sponsor allowlist / sponsor reference CSV | `data/sponsor_allowlist.csv` (create if needed; mounted in Docker) |

SQLite DB lives at `data/career_ops.db` (created on first use).

## Local setup

```bash
cd career-ops-cursor
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Daily scheduler (separate terminal):

```bash
python scripts/run_daily_scheduler.py
```

Edit scrape URLs in `config/scrape_sources.yml`.

## Docker

Dashboard only:

```bash
docker compose up --build web
```

Dashboard + daily scheduler (08:30 local container time):

```bash
docker compose --profile scheduler up --build
```

`./data` and `./output` are mounted into `/app/data` and `/app/output`.
