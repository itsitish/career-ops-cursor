"""
SQLite persistence for jobs, applications, and knowledge-base entries.

Database file: ``data/career_ops.db`` under the project root (parent of ``app/``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Project root: .../career-ops-cursor (parent of app/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = _PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "career_ops.db"


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def get_db_path() -> Path:
    """Return absolute path to the SQLite database file."""
    return DB_PATH


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Ensure the data directory exists and create tables if missing.

    Args:
        db_path: Optional override for the database file path.
    """
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                link TEXT NOT NULL UNIQUE,
                salary_text TEXT,
                location TEXT,
                source TEXT,
                jd_text TEXT,
                ats_score REAL,
                status TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                role TEXT NOT NULL,
                link TEXT NOT NULL,
                date_applied TEXT NOT NULL,
                status TEXT,
                cv_version TEXT,
                cover_version TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS kb_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_type TEXT NOT NULL,
                content TEXT NOT NULL,
                source_file TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_applications_date ON applications(date_applied);
            CREATE INDEX IF NOT EXISTS idx_kb_entry_type ON kb_entries(entry_type);
            """
        )
        conn.commit()
    finally:
        conn.close()


def _connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a SQLite connection with row factory."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# --- Jobs CRUD ---


def job_insert(
    company: str,
    role: str,
    link: str,
    *,
    salary_text: Optional[str] = None,
    location: Optional[str] = None,
    source: Optional[str] = None,
    jd_text: Optional[str] = None,
    ats_score: Optional[float] = None,
    status: Optional[str] = None,
    created_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Insert a job row; ``created_at`` defaults to UTC ISO time. Returns new row id."""
    init_db(db_path)
    ts = created_at or _utc_now_iso()
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO jobs (
                company, role, link, salary_text, location, source,
                jd_text, ats_score, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                role,
                link,
                salary_text,
                location,
                source,
                jd_text,
                ats_score,
                status,
                ts,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def job_get_by_id(job_id: int, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Return one job as a dict, or None if not found."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def job_get_by_link(link: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Return one job by unique ``link``, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE link = ?", (link,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def job_list(
    *,
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List jobs with optional ``status`` filter."""
    conn = _connect(db_path)
    try:
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def job_update(
    job_id: int,
    *,
    company: Optional[str] = None,
    role: Optional[str] = None,
    link: Optional[str] = None,
    salary_text: Optional[str] = None,
    location: Optional[str] = None,
    source: Optional[str] = None,
    jd_text: Optional[str] = None,
    ats_score: Optional[float] = None,
    status: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update non-None fields for ``job_id``. Returns True if a row was updated."""
    fields: list[str] = []
    values: list[Any] = []
    mapping = {
        "company": company,
        "role": role,
        "link": link,
        "salary_text": salary_text,
        "location": location,
        "source": source,
        "jd_text": jd_text,
        "ats_score": ats_score,
        "status": status,
    }
    for col, val in mapping.items():
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return False
    values.append(job_id)
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def job_delete(job_id: int, db_path: Optional[Path] = None) -> bool:
    """Delete a job by id. Returns True if a row was removed."""
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- Applications CRUD ---


def application_insert(
    company: str,
    role: str,
    link: str,
    date_applied: str,
    *,
    status: Optional[str] = None,
    cv_version: Optional[str] = None,
    cover_version: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Insert an application row. Returns new row id."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO applications (
                company, role, link, date_applied, status,
                cv_version, cover_version, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                company,
                role,
                link,
                date_applied,
                status,
                cv_version,
                cover_version,
                notes,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def application_get_by_id(
    application_id: int, db_path: Optional[Path] = None
) -> Optional[dict[str, Any]]:
    """Return one application as a dict, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM applications WHERE id = ?", (application_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def application_list(
    *,
    limit: int = 100,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List applications newest-first by id."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM applications ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def application_update(
    application_id: int,
    *,
    company: Optional[str] = None,
    role: Optional[str] = None,
    link: Optional[str] = None,
    date_applied: Optional[str] = None,
    status: Optional[str] = None,
    cv_version: Optional[str] = None,
    cover_version: Optional[str] = None,
    notes: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update non-None fields. Returns True if a row was updated."""
    fields: list[str] = []
    values: list[Any] = []
    mapping = {
        "company": company,
        "role": role,
        "link": link,
        "date_applied": date_applied,
        "status": status,
        "cv_version": cv_version,
        "cover_version": cover_version,
        "notes": notes,
    }
    for col, val in mapping.items():
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return False
    values.append(application_id)
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE applications SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def application_delete(application_id: int, db_path: Optional[Path] = None) -> bool:
    """Delete an application by id. Returns True if removed."""
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM applications WHERE id = ?", (application_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- KB entries CRUD ---


def kb_insert(
    entry_type: str,
    content: str,
    *,
    source_file: Optional[str] = None,
    created_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Insert a knowledge-base entry. Returns new row id."""
    init_db(db_path)
    ts = created_at or _utc_now_iso()
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO kb_entries (entry_type, content, source_file, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (entry_type, content, source_file, ts),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def kb_get_by_id(
    entry_id: int, db_path: Optional[Path] = None
) -> Optional[dict[str, Any]]:
    """Return one KB entry, or None."""
    conn = _connect(db_path)
    try:
        row = conn.execute("SELECT * FROM kb_entries WHERE id = ?", (entry_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def kb_list(
    *,
    entry_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List KB entries, optionally filtered by ``entry_type``."""
    conn = _connect(db_path)
    try:
        if entry_type is not None:
            rows = conn.execute(
                """
                SELECT * FROM kb_entries WHERE entry_type = ?
                ORDER BY id DESC LIMIT ? OFFSET ?
                """,
                (entry_type, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM kb_entries ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def kb_update(
    entry_id: int,
    *,
    entry_type: Optional[str] = None,
    content: Optional[str] = None,
    source_file: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> bool:
    """Update non-None fields. Returns True if a row was updated."""
    fields: list[str] = []
    values: list[Any] = []
    mapping = {"entry_type": entry_type, "content": content, "source_file": source_file}
    for col, val in mapping.items():
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return False
    values.append(entry_id)
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            f"UPDATE kb_entries SET {', '.join(fields)} WHERE id = ?", values
        )
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def kb_delete(entry_id: int, db_path: Optional[Path] = None) -> bool:
    """Delete a KB entry by id. Returns True if removed."""
    conn = _connect(db_path)
    try:
        cur = conn.execute("DELETE FROM kb_entries WHERE id = ?", (entry_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


@dataclass
class Storage:
    """
    Optional facade grouping DB path for tests or multi-db use.

    Methods delegate to module-level functions with ``db_path`` set.
    """

    db_path: Path = DB_PATH

    def init(self) -> None:
        """Create schema if needed."""
        init_db(self.db_path)

    def job_insert(self, **kwargs: Any) -> int:
        """Insert job; passes ``db_path``."""
        return job_insert(**kwargs, db_path=self.db_path)

    def job_get_by_id(self, job_id: int) -> Optional[dict[str, Any]]:
        return job_get_by_id(job_id, db_path=self.db_path)

    def job_get_by_link(self, link: str) -> Optional[dict[str, Any]]:
        return job_get_by_link(link, db_path=self.db_path)

    def job_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return job_list(**kwargs, db_path=self.db_path)

    def job_update(self, job_id: int, **kwargs: Any) -> bool:
        return job_update(job_id, **kwargs, db_path=self.db_path)

    def job_delete(self, job_id: int) -> bool:
        return job_delete(job_id, db_path=self.db_path)

    def application_insert(self, **kwargs: Any) -> int:
        return application_insert(**kwargs, db_path=self.db_path)

    def application_get_by_id(self, application_id: int) -> Optional[dict[str, Any]]:
        return application_get_by_id(application_id, db_path=self.db_path)

    def application_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return application_list(**kwargs, db_path=self.db_path)

    def application_update(self, application_id: int, **kwargs: Any) -> bool:
        return application_update(application_id, **kwargs, db_path=self.db_path)

    def application_delete(self, application_id: int) -> bool:
        return application_delete(application_id, db_path=self.db_path)

    def kb_insert(self, **kwargs: Any) -> int:
        return kb_insert(**kwargs, db_path=self.db_path)

    def kb_get_by_id(self, entry_id: int) -> Optional[dict[str, Any]]:
        return kb_get_by_id(entry_id, db_path=self.db_path)

    def kb_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        return kb_list(**kwargs, db_path=self.db_path)

    def kb_update(self, entry_id: int, **kwargs: Any) -> bool:
        return kb_update(entry_id, **kwargs, db_path=self.db_path)

    def kb_delete(self, entry_id: int) -> bool:
        return kb_delete(entry_id, db_path=self.db_path)
