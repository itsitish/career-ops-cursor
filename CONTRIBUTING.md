# Contributing

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

## Project layout

- `app/main.py` — FastAPI routes and dashboard wiring.
- `app/services/` — Workers (scrape, ATS, CV tailor), storage, PDF export.
- `app/settings.py` — Loads `config/profile.yml` or `profile.example.yml`.
- `config/` — `profile.example.yml`, `scrape_sources.yml`.

## Guidelines

- Prefer **deterministic**, testable helpers for prompt building (`app/services/prompt_analysis.py`).
- Keep **personal data** out of committed `config/profile.yml` (use the example + gitignore).
- Match existing style: type hints, short docstrings on public functions.

## Pull requests

Describe the behavior change, how to verify (e.g. tailor → ingest → PDF), and any config or schema updates.
