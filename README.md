# Career Ops (Cursor)

Local-first job application assistant: **knowledge base**, **JD scoring**, **Cursor-ready tailor prompts**, **ingest JSON from Cursor**, and **PDF export**. No external LLM API is required — you paste the generated prompt into Cursor chat and paste the JSON response back.

## Features

- **Master CV** — Upload via Knowledge Base; tailor prompts auto-load it when the override field is empty.
- **Rich Cursor prompt** — JD excerpts, keyword ↔ evidence table, strict no-fabrication rules. Profile fields (`target_roles`, headline, visa notes) are **not** injected into the tailor prompt (they still drive ATS scoring from `config/profile.yml`).
- **Copy/paste workflow** — Optional cover letter in the prompt (checkbox). Ingest validates JSON; cover required only when that box was checked for tailor + ingest.
- **ATS-style JD score** — Keyword overlap vs `target_roles`, salary heuristic, hard reject when the JD states no sponsorship (patterns in `app/services/ats_worker.py`).
- **Scraping** — `requests` + BeautifulSoup; URLs from `config/scrape_sources.yml`. LinkedIn search pages use extra selectors for title, subtitle (company · location), and salary when the HTML includes job cards. **If LinkedIn returns a login wall or a JS-only shell, cards may be empty** — use boards that serve real HTML (Greenhouse, etc.) or paste listings manually.
- **Jobs board** — Scrollable recent jobs table; **Remove** deletes a row via `DELETE /api/jobs/{id}`.
- **SQLite** — `data/career_ops.db`; uploads under `data/uploads/`; PDFs under `output/resumes/`.

## Configuration (open source)

1. Copy [`config/profile.example.yml`](config/profile.example.yml) to `config/profile.yml`.
2. Set `target_roles`, `compensation.minimum_gbp`, and optional `location.visa_sponsorship_note` and `candidate.headline`.
3. See [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) and [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md).

## Run locally

```bash
cd career-ops-cursor
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

## Docker

```bash
docker compose up --build web
```

Mounts `./data` and `./output`.

## Daily scheduler (optional)

```bash
python scripts/run_daily_scheduler.py
```

Edit `config/scrape_sources.yml`. Salary floor follows `compensation.minimum_gbp` in your profile.

## API highlights

| Endpoint | Purpose |
|----------|---------|
| `GET /api/kb` | List KB entries (`limit`, `offset`, optional `entry_type`) |
| `GET /api/kb/{id}` | One KB row including full `content` |
| `DELETE /api/kb/{id}` | Delete a KB row |
| `POST /api/jobs/tailor-prompt` | Build Cursor-ready prompt (`jd_text`, optional `master_cv_markdown`, `cover_requested`) |
| `POST /api/jobs/ingest-cursor-response` | Parse pasted JSON (`response_text`, `cover_requested`) |
| `POST /api/cv/export-pdf` | PDF from markdown |
| `POST /api/jobs/score` | ATS-style score (`jd_text`, optional `target_roles`, `required_salary_gbp`) |
| `DELETE /api/jobs/{id}` | Remove one scraped job row |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Add a `LICENSE` file when you publish the repo (e.g. MIT).
