"""
SQLite persistence for jobs, applications, and knowledge-base entries.

Database file: ``data/career_ops.db`` under the project root (parent of ``app/``).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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

# Strip common tracking params so the same job URL scraped twice still matches one row.
_TRACKING_QUERY_KEYS = frozenset(
    {"fbclid", "gclid", "mc_eid", "_ga", "igshid"}
)


def normalize_job_link(url: str) -> str:
    """
    Canonicalize a job listing URL for deduplication.

    Lowercases scheme and host, trims trailing slashes on the path, drops ``utm_*``
    and other tracking query keys, strips fragments, and sorts remaining query pairs.
    """
    u = (url or "").strip()
    if not u:
        return ""
    try:
        parsed = urlparse(u)
        scheme = (parsed.scheme or "https").lower()
        if scheme not in ("http", "https"):
            scheme = "https"
        netloc = (parsed.netloc or "").lower()
        path = parsed.path or ""
        if not path.startswith("/"):
            path = "/" + path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered: list[tuple[str, str]] = []
        for k, v in pairs:
            kl = k.lower()
            if kl.startswith("utm_") or kl in _TRACKING_QUERY_KEYS:
                continue
            filtered.append((k, v))
        filtered.sort(key=lambda x: (x[0].lower(), x[1]))
        query = urlencode(filtered)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return u


def job_find_for_upsert(listing_link: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """
    Find an existing job row for the same listing as ``listing_link``.

    Matches by normalized URL so ``http`` vs ``https``, trailing slashes, or ``utm_``
    params still resolve to the same row. Falls back to a bounded scan for legacy rows
    stored before normalization.
    """
    raw = (listing_link or "").strip()
    if not raw:
        return None
    canon = normalize_job_link(raw) or raw

    row = job_get_by_link(canon, db_path)
    if row:
        return dict(row)
    row = job_get_by_link(raw, db_path)
    if row:
        return dict(row)

    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT 5000"
        ).fetchall()
        for r in rows:
            if normalize_job_link(str(r["link"])) == canon:
                return dict(r)
    finally:
        conn.close()
    return None


def job_upsert_from_listing(
    listing: Dict[str, Any],
    *,
    insert_status: str = "scraped",
    db_path: Optional[Path] = None,
) -> Optional[str]:
    """
    Insert or update one scraped listing using normalized URL deduplication.

    Returns:
        ``\"inserted\"``, ``\"updated\"``, or ``None`` if ``link`` is missing.
    """
    link_raw = (listing.get("link") or "").strip()
    if not link_raw:
        return None
    link = normalize_job_link(link_raw) or link_raw
    company = str(listing.get("company") or "")
    role = str(listing.get("role") or "Unknown role")
    salary_text = listing.get("salary_text")
    location = listing.get("location")
    source = listing.get("source")
    jd_text = listing.get("jd_text")
    existing = job_find_for_upsert(link_raw, db_path)
    if existing:
        job_update(
            int(existing["id"]),
            company=company or None,
            role=role,
            link=link,
            salary_text=salary_text,
            location=location,
            source=source,
            jd_text=jd_text,
            db_path=db_path,
        )
        return "updated"
    job_insert(
        company=company or "Unknown",
        role=role,
        link=link,
        salary_text=salary_text,
        location=location,
        source=source,
        jd_text=jd_text,
        status=insert_status,
        db_path=db_path,
    )
    return "inserted"


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
    """
    List jobs with optional ``status`` filter, newest first.

    Deduplicates by :func:`normalize_job_link` so the Recent jobs board does not show
    multiple rows for the same listing (legacy duplicates or URL variants). Fetches
    extra rows from SQLite then trims to ``limit`` unique canonical links.
    """
    fetch_cap = min(max(limit * 10, limit + 20), 8000)
    conn = _connect(db_path)
    try:
        if status is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (status, fetch_cap, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY id DESC LIMIT ? OFFSET ?",
                (fetch_cap, offset),
            ).fetchall()
    finally:
        conn.close()

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        raw_link = str(d.get("link") or "")
        key = normalize_job_link(raw_link) or raw_link
        if key in seen:
            continue
        seen.add(key)
        out.append(d)
        if len(out) >= limit:
            break
    return out


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
        """Return one job row using the facade's configured ``db_path``."""
        return job_get_by_id(job_id, db_path=self.db_path)

    def job_get_by_link(self, link: str) -> Optional[dict[str, Any]]:
        """Return the job row matching ``link`` using the facade's ``db_path``."""
        return job_get_by_link(link, db_path=self.db_path)

    def job_find_for_upsert(self, listing_link: str) -> Optional[dict[str, Any]]:
        """Resolve an existing job row for ``listing_link`` (normalized matching)."""
        return job_find_for_upsert(listing_link, db_path=self.db_path)

    def job_upsert_from_listing(
        self, listing: Dict[str, Any], *, insert_status: str = "scraped"
    ) -> Optional[str]:
        """Insert or update one scraped listing using this facade's ``db_path``."""
        return job_upsert_from_listing(
            listing, insert_status=insert_status, db_path=self.db_path
        )

    def job_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List jobs via the facade's configured database path."""
        return job_list(**kwargs, db_path=self.db_path)

    def job_update(self, job_id: int, **kwargs: Any) -> bool:
        """Update one job row using the facade's configured ``db_path``."""
        return job_update(job_id, **kwargs, db_path=self.db_path)

    def job_delete(self, job_id: int) -> bool:
        """Delete one job row using the facade's configured ``db_path``."""
        return job_delete(job_id, db_path=self.db_path)

    def application_insert(self, **kwargs: Any) -> int:
        """Insert an application row using the facade's configured ``db_path``."""
        return application_insert(**kwargs, db_path=self.db_path)

    def application_get_by_id(self, application_id: int) -> Optional[dict[str, Any]]:
        """Return one application row using the facade's configured ``db_path``."""
        return application_get_by_id(application_id, db_path=self.db_path)

    def application_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List applications via the facade's configured database path."""
        return application_list(**kwargs, db_path=self.db_path)

    def application_update(self, application_id: int, **kwargs: Any) -> bool:
        """Update one application row using the facade's configured ``db_path``."""
        return application_update(application_id, **kwargs, db_path=self.db_path)

    def application_delete(self, application_id: int) -> bool:
        """Delete one application row using the facade's configured ``db_path``."""
        return application_delete(application_id, db_path=self.db_path)

    def kb_insert(self, **kwargs: Any) -> int:
        """Insert one KB row using the facade's configured ``db_path``."""
        return kb_insert(**kwargs, db_path=self.db_path)

    def kb_get_by_id(self, entry_id: int) -> Optional[dict[str, Any]]:
        """Return one KB row using the facade's configured ``db_path``."""
        return kb_get_by_id(entry_id, db_path=self.db_path)

    def kb_list(self, **kwargs: Any) -> list[dict[str, Any]]:
        """List KB rows via the facade's configured database path."""
        return kb_list(**kwargs, db_path=self.db_path)

    def kb_update(self, entry_id: int, **kwargs: Any) -> bool:
        """Update one KB row using the facade's configured ``db_path``."""
        return kb_update(entry_id, **kwargs, db_path=self.db_path)

    def kb_delete(self, entry_id: int) -> bool:
        """Delete one KB row using the facade's configured ``db_path``."""
        return kb_delete(entry_id, db_path=self.db_path)
