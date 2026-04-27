#!/usr/bin/env python3
"""
Daily scrape scheduler: loads URLs from config, runs ScraperWorker, persists via Storage.

Schedules one job per day at 08:30 in the host's local timezone using APScheduler.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler

# Project root (parent of scripts/)
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.settings import load_settings  # noqa: E402
from app.services.scraper_worker import ScraperWorker  # noqa: E402
from app.services.storage import Storage, job_upsert_from_listing  # noqa: E402

_CONFIG_PATH = _ROOT / "config" / "scrape_sources.yml"


def _load_urls() -> list[str]:
    """Read ``urls`` list from ``config/scrape_sources.yml``."""
    if not _CONFIG_PATH.is_file():
        raise FileNotFoundError(f"Missing config: {_CONFIG_PATH}")
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    urls_raw = raw.get("urls", [])
    if not isinstance(urls_raw, list):
        raise ValueError("scrape_sources.yml: 'urls' must be a list")
    return [str(u).strip() for u in urls_raw if str(u).strip()]


def _run_scrape_and_store() -> dict[str, Any]:
    """
    Execute one scrape pass: ScraperWorker with ``min_salary_gbp`` then Storage inserts.

    Returns:
        Summary dict suitable for logging (counts, flags).
    """
    urls = _load_urls()
    settings = load_settings(_ROOT)
    worker = ScraperWorker()
    storage = Storage()
    storage.init()

    task = {
        "task_type": "scrape_jobs",
        "payload": {
            "urls": urls,
            "min_salary_gbp": settings.min_salary_gbp,
        },
    }
    result = worker.process(task)

    inserted = 0
    updated = 0
    if result.get("ok") and result.get("listings"):
        for listing in result["listings"]:
            op = job_upsert_from_listing(
                listing, insert_status="new", db_path=storage.db_path
            )
            if op == "inserted":
                inserted += 1
            elif op == "updated":
                updated += 1

    err_count = len(result.get("errors") or [])
    listing_count = len(result.get("listings") or [])

    summary = {
        "ok": bool(result.get("ok")),
        "urls": len(urls),
        "listings": listing_count,
        "inserted": inserted,
        "updated_existing": updated,
        "errors": err_count,
        "min_salary_gbp": result.get("min_salary_gbp", settings.min_salary_gbp),
    }
    return summary


def _print_summary(s: dict[str, Any]) -> None:
    """Emit a single-line human-readable run summary."""
    parts = [
        f"ok={s['ok']}",
        f"urls={s['urls']}",
        f"listings={s['listings']}",
        f"inserted={s['inserted']}",
        f"updated={s['updated_existing']}",
        f"errors={s['errors']}",
        f"min_gbp={s['min_salary_gbp']}",
    ]
    print("daily_scrape: " + " ".join(parts))


def scheduled_job() -> None:
    """APScheduler entrypoint for the daily scrape."""
    summary = _run_scrape_and_store()
    _print_summary(summary)


def main() -> None:
    """Start BlockingScheduler: daily cron at 08:30 local time."""
    settings = load_settings(_ROOT)
    scheduler = BlockingScheduler()
    scheduler.add_job(
        scheduled_job,
        "cron",
        hour=8,
        minute=30,
        id="daily_scrape",
        replace_existing=True,
    )
    print(
        "Scheduler running: daily scrape at 08:30 local time "
        f"(config={_CONFIG_PATH}, min_salary_gbp={settings.min_salary_gbp})"
    )
    scheduler.start()


if __name__ == "__main__":
    main()
