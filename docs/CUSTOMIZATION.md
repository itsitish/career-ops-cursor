# Customization

## Profile (`config/profile.yml`)

Copy `config/profile.example.yml` to `config/profile.yml` (gitignored).

| Section | Purpose |
|---------|---------|
| `candidate.headline` | Optional; for your own CV copy (not injected into the generated tailor prompt). |
| `target_roles.primary` | List of role titles for ATS keyword overlap and scoring. |
| `target_roles.archetypes` | Optional `{ name, level, fit }` entries; names are appended to target roles for scoring. |
| `compensation.minimum_gbp` | Minimum acceptable salary (GBP) for scrape default and JD score API default. |
| `location.visa_sponsorship_note` | Free text for your records / CV (not injected into the generated tailor prompt). |
| `locale` | `en-GB` or `en-US` — hints spelling in generated prompts. |

## Scrape sources

Edit `config/scrape_sources.yml` — list of URLs for `POST /api/scrape/run` and the daily scheduler.

## Knowledge base

Upload CVs and documents via the dashboard. The latest upload whose filename contains `master` and `cv` is used as the master CV when the tailor form override is empty.
