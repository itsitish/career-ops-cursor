# Data contract

## User-owned (do not commit secrets)

| Path | Purpose |
|------|---------|
| `config/profile.yml` | Personal targets, salary floor, visa notes — copy from `profile.example.yml`. |
| `data/career_ops.db` | SQLite database (local). |
| `data/uploads/*` | Uploaded KB files. |
| `output/resumes/*`, `output/covers/*` | Generated PDFs. |
| `.env` | Optional local overrides (currently minimal). |

## Shipped / safe to version

| Path | Purpose |
|------|---------|
| `config/profile.example.yml` | Template profile for contributors. |
| `config/scrape_sources.yml` | Example scrape URL list. |
| `app/**` | Application code. |

Updates to the repo should not overwrite a user's `config/profile.yml` or database.
