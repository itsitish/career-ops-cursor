# Career Ops (Cursor)

Local-first job application workspace for managing a reusable career knowledge base, scoring job descriptions, generating Cursor-ready CV prompts, ingesting Cursor JSON output, tracking applications, scraping job boards, and exporting final CV / cover PDFs.

The app does **not** call an external LLM API. It builds deterministic prompts and local helper output; you paste the prompt into Cursor chat, then paste Cursor's strict JSON response back into the dashboard.

## Quick Start

### Local

```bash
cd career-ops-cursor
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://127.0.0.1:8000`.

### Docker

```bash
docker compose up --build web
```

Open `http://127.0.0.1:8000`.

The Docker service mounts local folders into the container:

- `./config` to `/app/config`
- `./data` to `/app/data`
- `./output` to `/app/output`

## Setup

1. Copy `config/profile.example.yml` to `config/profile.yml`.
2. Set `target_roles.primary` and `compensation.minimum_gbp`.
3. Keep your canonical CV in `config/master_profile.md`.
4. Add extra notes/files through the Knowledge Base if needed.

`config/profile.yml`, `data/`, and `output/` are local runtime files and should not be committed.

More detail:

- `docs/CUSTOMIZATION.md`
- `docs/DATA_CONTRACT.md`

## Product Workflow

1. **Knowledge Base**: add notes or upload `.md`, `.txt`, `.docx`, or `.pdf` files.
2. **KB Digest**: each KB add/upload/delete refreshes `config/kb_digest.md` for Cursor `@` reference.
3. **Job Description Analysis**: paste a JD and generate a Cursor prompt.
4. **Cursor Chat**: attach `@config/master_profile.md` and `@config/kb_digest.md`, then paste the generated prompt.
5. **Ingest Cursor Response**: paste Cursor's JSON back into the app.
6. **Export PDF**: save CV PDFs to `output/resumes/` and cover PDFs to `output/covers/`.
7. **Operations**: scrape jobs, maintain recent jobs, and track application status.

Master CV resolution order for tailoring:

1. non-empty dashboard override
2. `config/master_profile.md`
3. latest suitable KB upload, preferring filenames containing both `master` and `cv`

## Codebase Summary

### Application Entry Point

`app/main.py` defines the FastAPI app, lifecycle setup, dashboard rendering, and all HTTP routes. Startup loads `.env`, initialises SQLite, ensures `data/uploads/`, loads profile settings, registers workers, starts the monitor dispatcher, and initialises in-memory latest prompt/CV/cover state.

Key helper responsibilities in `app/main.py`:

- upload text extraction for `.docx`, `.pdf`, `.txt`, and `.md`
- KB row summaries and digest generation
- master CV resolution
- scrape source loading
- short synchronous waiting for monitor tasks
- Cursor prompt wrapping and strict JSON output instructions

### Dashboard Frontend

`app/templates/index.html` is a single Jinja-rendered dashboard with inline CSS and JavaScript. It contains four tabbed sections:

- **Job Description Analysis**: score JDs and generate Cursor prompts.
- **CV & Cover Output**: ingest Cursor JSON and export CV / cover PDFs.
- **Knowledge Base**: add text, upload files, list/view/delete KB entries, and manually save the digest.
- **Operations & Monitoring**: show scraped jobs, run scrapes, add/update/delete applications, and view monitor snapshots.

The frontend uses `fetch` for JSON APIs, dynamically updates KB/application/job tables, persists sidebar visibility in `localStorage`, and includes a floating dark-blue scroll-to-top button.

### Storage Layer

`app/services/storage.py` owns SQLite persistence in `data/career_ops.db`.

Tables:

- `jobs`: scraped listings with unique normalised `link`, salary/location/source/JD/score/status metadata.
- `applications`: local application tracker with company, role, link, date, status, CV version, cover version, and notes.
- `kb_entries`: reusable notes/uploads with entry type, content, source file, and timestamp.

The module also provides URL normalisation and upsert logic for scraped jobs so repeated scrape runs update existing rows instead of duplicating listings.

### Worker System

`app/services/agent_bus.py` defines task lifecycle records and statuses.

`app/services/monitor_agent.py` is a small local dispatcher. It queues tasks, picks a registered worker by task type, runs work in background threads, tracks worker status, and exposes snapshots for the dashboard.

Registered workers:

- `ScraperWorker` handles `scrape_jobs`.
- `AtsScoringWorker` handles `score_jd`.
- `CvTailorWorker` handles `tailor_cv_prompt`.

### JD Scoring

`app/services/ats_worker.py` scores a JD against configured target roles. It extracts JD keywords, compares them with target role vocabulary, parses salary signals against the configured GBP floor, and applies hard rejection when the JD indicates no visa/sponsorship or incompatible right-to-work constraints.

### Prompt Generation

`app/services/cv_tailor_worker.py` builds deterministic Cursor prompts from:

- verbatim JD text
- master CV markdown
- deduplicated KB highlights
- JD requirement snippets
- keyword-to-evidence table
- formatting and truthfulness constraints

Prompt guidance currently enforces British English, standard Markdown, no horizontal rules, no Unicode arrows/non-Markdown symbols, no fabricated facts, and plain-text education module/focus lines. It can optionally request a cover letter and returns a review checklist.

`app/services/prompt_analysis.py` contains deterministic JD analysis helpers: must-have line extraction, top keyword extraction, keyword evidence mapping, and the British English instruction.

### Cursor Response Parsing

`app/services/cursor_response.py` parses pasted Cursor responses. It strips optional JSON fences, validates the required JSON shape, removes standalone Markdown thematic-break lines (`---`, `***`, `___`), and returns clean `tailored_cv_markdown` and optional `tailored_cover_markdown`.

`app/services/md_preview.py` provides a safe, escaped Markdown-to-HTML preview helper for a small subset of Markdown. The current dashboard primarily uses the raw markdown textareas for PDF export, but the helper remains available for preview rendering.

### PDF Export

`app/services/pdf_export.py` uses `fpdf2` to convert markdown-like text to PDF.

- CV export writes to `output/resumes/`.
- Cover export writes to `output/covers/`.
- CVs use a styled top banner and body split around `## Core Skills` / similar section headings.
- Cover letters render as simple left-aligned letters with no CV banner/divider.
- Inline `**bold**`, headings, word wrapping, and common ATS-safe punctuation replacements are supported.

### Scraping

`app/services/scraper_worker.py` uses `requests` and BeautifulSoup to scrape job listings from configured URLs. It uses heuristic card extraction, salary parsing/filtering, source-aware selectors, per-URL error handling, and returns listing dictionaries for storage upsert.

`config/scrape_sources.yml` stores the URL list used by both the dashboard scrape form and scheduler.

### Settings And Config

`app/settings.py` loads `config/profile.yml` when present, otherwise `config/profile.example.yml`. It supports:

- `target_roles.primary`
- optional `target_roles.archetypes`
- `compensation.minimum_gbp`
- `location.visa_sponsorship_note`
- `candidate.headline`
- `locale` / `locale_hint`

The current prompt policy always uses British English even though the settings loader still accepts locale fields for compatibility.

Important config files:

- `config/profile.example.yml`: copy this to `config/profile.yml`.
- `config/master_profile.md`: recommended canonical master CV.
- `config/kb_digest.md`: generated digest of KB rows for Cursor `@` reference.
- `config/chat_instruction.md`: persistent rules to paste/use in Cursor chat alongside master/digest context.
- `config/scrape_sources.yml`: scrape URLs.

### Scripts

`scripts/run_daily_scheduler.py` runs an APScheduler blocking process. It loads URLs from `config/scrape_sources.yml`, uses `ScraperWorker`, stores listings through the shared job upsert path, and schedules a daily scrape at 08:30 local time.

Run locally:

```bash
python scripts/run_daily_scheduler.py
```

Run with Docker:

```bash
docker compose --profile scheduler up --build scheduler
```

`scripts/agent_monitor_demo.py` is a small demo for the local monitor/worker system.

### Docker

`Dockerfile` builds a Python 3.12 slim image, installs `requirements.txt`, copies the repo, exposes port `8000`, and runs `uvicorn app.main:app`.

`docker-compose.yml` defines:

- `web`: dashboard/API service on port `8000`
- `scheduler`: optional profile service for the daily scraper

## API Reference

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Render dashboard |
| `POST /api/kb/add-text` | Add text note to KB and refresh digest |
| `POST /api/kb/upload` | Upload `.md`, `.txt`, `.docx`, or `.pdf`; extract text into KB and refresh digest |
| `GET /api/kb` | List KB rows with previews |
| `GET /api/kb/{id}` | Read one full KB row |
| `DELETE /api/kb/{id}` | Delete KB row and refresh digest |
| `GET /api/kb/export.md` | Return KB digest markdown |
| `POST /api/kb/write-digest` | Write `config/kb_digest.md` manually |
| `POST /api/jobs/score` | Score a JD using the local ATS worker |
| `POST /api/jobs/tailor-prompt` | Generate Cursor-ready tailor prompt |
| `POST /api/jobs/ingest-cursor-response` | Parse Cursor JSON and store latest tailored markdown in app state |
| `POST /api/scrape/run` | Scrape configured/manual URLs and upsert listings |
| `DELETE /api/jobs/{id}` | Delete scraped job row |
| `POST /api/applications/add` | Add application tracker row |
| `PATCH /api/applications/{id}` | Update application fields/status |
| `DELETE /api/applications/{id}` | Delete application row |
| `POST /api/cv/export-pdf` | Export CV/cover markdown to PDF (`document: "cv"` or `"cover"`) |
| `GET /api/monitor` | Return queue/worker snapshot |

## Data And Output Locations

- `data/career_ops.db`: SQLite database
- `data/uploads/`: uploaded KB files
- `output/resumes/`: generated CV PDFs
- `output/covers/`: generated cover letter PDFs
- `config/profile.yml`: local settings, gitignored
- `config/master_profile.md`: recommended master CV source
- `config/kb_digest.md`: generated KB digest
- `.env`: optional local environment overrides

The app creates `data/` and `output/` as needed.

## Dependencies

Runtime dependencies are listed in `requirements.txt`:

- FastAPI / Uvicorn / Jinja2 for the dashboard and API
- SQLite from the Python standard library for persistence
- `python-docx` and `pypdf` for upload text extraction
- `requests` and BeautifulSoup for scraping
- APScheduler for daily scraping
- PyYAML for config
- `fpdf2` for PDF export

## Troubleshooting

- **No master CV found**: add `config/master_profile.md`, upload a master CV to KB, or paste master markdown into the tailor form.
- **Prompt output is weak**: confirm the JD is complete, `config/master_profile.md` is current, and `config/kb_digest.md` has relevant facts.
- **Cursor JSON ingest fails**: paste only the strict JSON object requested by the prompt.
- **LinkedIn scrape returns nothing**: LinkedIn often returns login walls or JavaScript shells; use non-LinkedIn sources or paste the JD manually.
- **Docker changes are missing**: rebuild the image and confirm `./config`, `./data`, and `./output` are mounted.

## Contributing

See `CONTRIBUTING.md`.
