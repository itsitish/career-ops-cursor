# Career Ops (Cursor)

Local-first job application assistant for:

- storing a reusable knowledge base
- scoring job descriptions against your target roles
- generating a Cursor-ready CV tailoring prompt
- ingesting Cursor JSON output back into the app
- exporting the final CV / cover letter to PDF

No external LLM API is required. The app generates a prompt, you paste it into Cursor chat, then you paste Cursor's JSON response back into the app.

## What You Need

- Python 3.12+ for local development
- or Docker / Docker Compose
- a master CV in `.md`, `.txt`, `.docx`, or `.pdf`

## Quick Start (Local)

```bash
cd career-ops-cursor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

`PYTHONPATH=.` lets `uvicorn` import the local `app` package when you run from the repo root.

## Quick Start (Docker)

```bash
docker compose up --build web
```

Then open `http://127.0.0.1:8000`.

The `web` service mounts:

- `./data` -> app database and uploads
- `./output` -> generated PDFs
- `./config` -> your local profile/config files

## Required Setup

1. Copy [`config/profile.example.yml`](config/profile.example.yml) to `config/profile.yml`.
2. Set at least:
   - `target_roles`
   - `compensation.minimum_gbp`
   - `locale` if you want `en-GB` vs `en-US` prompt guidance
3. Optional fields:
   - `candidate.headline`
   - `location.visa_sponsorship_note`

Important: profile fields still influence ATS scoring and defaults, but they are **not** pasted into the generated tailor prompt.

More detail:

- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md)
- [docs/DATA_CONTRACT.md](docs/DATA_CONTRACT.md)

## First-Use Workflow

For a new user, the fastest path is:

1. Open the dashboard.
2. In `Job Description Analysis`, paste a JD and generate the tailor prompt.
3. In `CV & Cover Output`, keep the generated prompt ready for Cursor.
4. In `Knowledge Base`, upload your master CV.
   - If the filename contains both `master` and `cv`, the app will prefer it as the default master CV for tailoring.
5. Copy the generated prompt into Cursor chat.
6. Paste Cursor's JSON response into `Ingest Cursor response`.
7. Review the tailored CV / cover markdown in the app.
8. Export the final PDF.

Recommended real usage order:

1. create `config/profile.yml`
2. upload the master CV to Knowledge Base
3. paste a JD
4. generate the prompt
5. run it in Cursor
6. ingest Cursor JSON
7. export PDF

## Main Features

- **Knowledge Base**: Store notes, achievements, and uploaded files. You can list, inspect, and delete KB rows from the dashboard.
- **JD scoring**: Compare a JD against your configured target roles and salary floor.
- **Tailor prompt generation**: Build a deterministic prompt with JD extracts, keyword evidence, pruning rules, and formatting guidance.
- **Copy/paste Cursor workflow**: Optional cover letter support; strict JSON response format.
- **PDF export**: Converts tailored markdown into a styled PDF with centered contact header and inline bold support.
- **Scraping**: Pull job listings from `config/scrape_sources.yml` using `requests` + BeautifulSoup.

## Scraping And Scheduler

Edit [`config/scrape_sources.yml`](config/scrape_sources.yml) to control scrape URLs.

Run one-off scheduler process locally:

```bash
python scripts/run_daily_scheduler.py
```

Run the scheduler with Docker:

```bash
docker compose --profile scheduler up --build scheduler
```

Notes:

- scheduler uses `compensation.minimum_gbp` from `config/profile.yml`
- LinkedIn search pages can return login walls or JS-only shells, so cards may be empty
- Greenhouse and other server-rendered boards are usually more reliable

## Data And Output Locations

- database: `data/career_ops.db`
- uploaded KB files: `data/uploads/`
- exported PDFs: `output/resumes/`
- local profile: `config/profile.yml`
- optional env overrides: `.env`

The app creates `data/` and `output/` as needed.

## API Highlights

| Endpoint | Purpose |
|----------|---------|
| `GET /api/kb` | List KB entries (`limit`, `offset`, optional `entry_type`) |
| `GET /api/kb/{id}` | Read one KB row including full `content` |
| `DELETE /api/kb/{id}` | Delete a KB row |
| `POST /api/jobs/score` | ATS-style score (`jd_text`, optional `target_roles`, `required_salary_gbp`) |
| `POST /api/jobs/tailor-prompt` | Build the Cursor-ready prompt |
| `POST /api/jobs/ingest-cursor-response` | Parse pasted Cursor JSON |
| `POST /api/cv/export-pdf` | Export markdown to PDF |
| `DELETE /api/jobs/{id}` | Remove a scraped job row |

## Troubleshooting

- **No master CV found**: upload a CV first in `Knowledge Base`, or paste one into the tailor form override.
- **Prompt looks fine but output is weak**: make sure the uploaded master CV is the latest intended version and the JD text is complete.
- **LinkedIn scrape returns nothing**: try a non-LinkedIn board or paste the JD manually.
- **Docker changes not reflected**: confirm `./config`, `./data`, and `./output` are mounted and you edited files in the repo root.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).
