# Career Ops (Cursor)

## What this is

- **Tailoring default** — With `CURSOR_USE_LLM=0` (or unset), CV/cover output is **local and deterministic** (same inputs → same markdown). No LLM required.
- **Optional LLM** — Copy `.env.example` to `.env`, set `CURSOR_USE_LLM=1`, `CURSOR_API_KEY`, and `CURSOR_OPENAI_BASE_URL` pointing at an **OpenAI-compatible** API whose **`/v1/chat/completions`** (or equivalent base + chat path) matches your provider. Set `CURSOR_MODEL` as needed (default in example: `gpt-4.1-mini`). If the provider call **fails**, the app **falls back** to the same local deterministic tailor.
- **Scraping** — uses `requests` / BeautifulSoup (no paid scrape APIs). You can still use **Cursor-in-the-loop** with the generated prompt markdown.
- **PDF output** — export tailored markdown via `POST /api/cv/export-pdf` to `output/resumes/`.
- **Salary**: listings are filtered at scrape time when a GBP salary parses below **£60,000** (`min_salary_gbp` in the scheduler).
- **Sponsorship**: the ATS worker **hard-rejects** job descriptions that clearly state no visa/sponsorship (see `app/services/ats_worker.py`).
- **Master CV auto-use** — `tailor-prompt` uses your latest uploaded master CV when manual CV text is left empty.

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
