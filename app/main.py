"""
FastAPI dashboard for career-ops: KB, JD scoring, CV tailor prompts, scraping, applications.
"""

from __future__ import annotations

import json
import os
import time
import uuid
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader

from app.services.agent_bus import TaskRecord, TaskStatus
from app.services.ats_worker import AtsScoringWorker
from app.services.cursor_response import parse_cursor_response_json
from app.services.cv_tailor_worker import CvTailorWorker
from app.services.monitor_agent import MonitorAgent
from app.services.pdf_export import markdown_to_pdf
from app.services.scraper_worker import ScraperWorker
from app.services import storage
from app.settings import AppSettings, load_settings
from docx import Document

# Templates live next to this package under app/templates/
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Uploaded files land under data/uploads/
_UPLOAD_DIR = storage.DATA_DIR / "uploads"

# Repository root (parent of ``app/``) for optional ``.env``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# KB list API / dashboard: max characters for one-line preview text.
_KB_PREVIEW_CHARS = 240


def _kb_summary_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Public fields for KB list (no full ``content`` body)."""
    content = str(row.get("content") or "")
    preview = " ".join(content.split())
    if len(preview) > _KB_PREVIEW_CHARS:
        preview = preview[:_KB_PREVIEW_CHARS] + "…"
    return {
        "id": int(row["id"]),
        "entry_type": row.get("entry_type") or "",
        "created_at": row.get("created_at") or "",
        "source_file": row.get("source_file") or "",
        "content_length": len(content),
        "content_preview": preview,
    }


def load_dotenv_file(path: Path) -> None:
    """
    Load ``KEY=value`` lines from ``path`` into ``os.environ`` when the key is unset.

    Supports ``#`` comments and blank lines. Strips optional single/double quotes
    around values. Does not implement full dotenv escaping rules.
    """
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, rest = stripped.partition("=")
        key = key.strip()
        if not key or key.startswith("#"):
            continue
        val = rest.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if key not in os.environ:
            os.environ[key] = val


def wait_for_task_terminal(
    monitor: MonitorAgent,
    task_id: str,
    timeout_s: float,
    poll_s: float = 0.05,
) -> tuple[Literal["completed", "failed", "timeout"], Optional[TaskRecord]]:
    """
    Poll the monitor's internal task registry until the task finishes or time runs out.

    Returns:
        A status label and the ``TaskRecord`` when completed/failed, or ``None`` on timeout
        (record may still be running/queued).
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with monitor._lock:
            rec = monitor._tasks.get(task_id)
            if rec is not None and rec.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
            ):
                return rec.status.value, rec  # type: ignore[return-value]
        time.sleep(poll_s)
    return "timeout", None


def extract_text_from_bytes(filename: str, data: bytes) -> str:
    """
    Extract plain text from upload bytes based on file extension.

    Supports ``.docx`` (python-docx), ``.pdf`` (pypdf), and ``.txt`` / ``.md`` as UTF-8 text.
    """
    from io import BytesIO

    lower = filename.lower()
    buf = BytesIO(data)
    if lower.endswith(".docx"):
        doc = Document(buf)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if lower.endswith(".pdf"):
        reader = PdfReader(buf)
        parts: List[str] = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)
    if lower.endswith(".txt") or lower.endswith(".md"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"unsupported extension for {filename!r}")


def upsert_job_listing(listing: Dict[str, Any]) -> Optional[Literal["inserted", "updated"]]:
    """
    Persist one scraped listing: insert new row or update existing row by unique ``link``.

    Returns:
        ``\"inserted\"``, ``\"updated\"``, or ``None`` if ``link`` is missing.
    """
    link = (listing.get("link") or "").strip()
    if not link:
        return None
    company = str(listing.get("company") or "")
    role = str(listing.get("role") or "Unknown role")
    salary_text = listing.get("salary_text")
    location = listing.get("location")
    source = listing.get("source")
    jd_text = listing.get("jd_text")
    existing = storage.job_get_by_link(link)
    if existing:
        storage.job_update(
            int(existing["id"]),
            company=company or None,
            role=role,
            link=link,
            salary_text=salary_text,
            location=location,
            source=source,
            jd_text=jd_text,
        )
        return "updated"
    storage.job_insert(
        company=company or "Unknown",
        role=role,
        link=link,
        salary_text=salary_text,
        location=location,
        source=source,
        jd_text=jd_text,
        status="scraped",
    )
    return "inserted"


def kb_highlights_latest(limit: int = 10) -> List[str]:
    """Return ``content`` strings from the newest KB rows (newest first)."""
    rows = storage.kb_list(limit=limit, offset=0)
    return [str(r["content"]) for r in rows]


def dedupe_kb_highlights(highlights: List[str]) -> List[str]:
    """
    Drop duplicate KB snippets by exact match after whitespace normalization.

    Comparison key: casefolded single-spaced string. Preserves first-seen order.
    """
    seen: set[str] = set()
    out: List[str] = []
    for h in highlights:
        s = str(h).strip()
        if not s:
            continue
        key = " ".join(s.split()).casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _kb_overlap_tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens (length > 2) for overlap checks."""
    return {m.group(0) for m in re.finditer(r"[a-z0-9]{3,}", text.lower())}


def filter_kb_highlights_vs_master_cv(highlights: List[str], master_cv: str) -> List[str]:
    """
    Drop KB highlights that largely duplicate master CV lines (substring or token coverage).

    Keeps concise highlights that add information beyond any single CV line; order preserved.
    """
    master_norm = " ".join(master_cv.split()).casefold()
    line_token_sets: List[set[str]] = []
    for line in master_cv.splitlines():
        s = line.strip()
        if len(s) < 10:
            continue
        ts = _kb_overlap_tokens(s)
        if len(ts) >= 4:
            line_token_sets.append(ts)

    def is_redundant(h: str) -> bool:
        raw = h.strip()
        if not raw:
            return True
        norm_h = " ".join(raw.split()).casefold()
        if len(norm_h) >= 28 and norm_h in master_norm:
            return True
        th = _kb_overlap_tokens(raw)
        if len(th) < 3:
            return False
        if not line_token_sets:
            return False
        best = max(len(th & lt) / len(th) for lt in line_token_sets)
        return best >= 0.72

    return [h.strip() for h in highlights if not is_redundant(h)]


def latest_master_cv_text() -> Optional[str]:
    """
    Return the best candidate master CV text from KB uploads.

    Preference order:
    1) Latest upload whose source filename contains ``master`` and ``cv``.
    2) Latest upload entry.
    """
    rows = storage.kb_list(limit=300, offset=0)
    uploads = [r for r in rows if str(r.get("entry_type") or "") == "upload"]
    if not uploads:
        return None

    for row in uploads:
        src = str(row.get("source_file") or "").lower()
        if "master" in src and "cv" in src:
            text = str(row.get("content") or "").strip()
            if text:
                return text

    fallback = str(uploads[0].get("content") or "").strip()
    return fallback or None


def build_copy_paste_prompt(base_prompt: str, *, cover_requested: bool = False) -> str:
    """
    Append strict JSON output instructions for the copy/paste Cursor workflow.

    When ``cover_requested`` is False, the model must return only ``tailored_cv_markdown``.
    """
    if cover_requested:
        suffix = (
            "\n\n## Output format (strict)\n"
            "Return ONLY valid JSON in this exact shape:\n"
            "{\n"
            '  "tailored_cv_markdown": "<markdown cv>",\n'
            '  "tailored_cover_markdown": "<markdown cover letter>"\n'
            "}\n"
            "No markdown fences, no extra commentary."
        )
    else:
        suffix = (
            "\n\n## Output format (strict)\n"
            "Return ONLY valid JSON in this exact shape:\n"
            "{\n"
            '  "tailored_cv_markdown": "<markdown cv>"\n'
            "}\n"
            "Do not add a cover letter field. No markdown fences, no extra commentary."
        )
    return f"{base_prompt.rstrip()}\n{suffix}\n"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, workers, monitor, and profile settings; tear down on exit."""
    load_dotenv_file(_PROJECT_ROOT / ".env")
    storage.init_db()
    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    settings = load_settings(_PROJECT_ROOT)
    app.state.settings = settings

    monitor = MonitorAgent()
    monitor.register_worker(ScraperWorker())
    monitor.register_worker(AtsScoringWorker())
    monitor.register_worker(CvTailorWorker())
    monitor.start()
    app.state.monitor = monitor
    app.state.latest_cursor_prompt = ""
    app.state.latest_tailored_cv = ""
    app.state.latest_tailored_cover = ""

    yield

    monitor.stop(timeout=8.0)


app = FastAPI(title="Career Ops", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> Any:
    """Render the HTML dashboard with recent jobs, applications, and monitor snapshot."""
    monitor: MonitorAgent = request.app.state.monitor
    settings: AppSettings = getattr(request.app.state, "settings", load_settings(_PROJECT_ROOT))
    jobs = storage.job_list(limit=30)
    applications = storage.application_list(limit=30)
    master_cv_prefill = latest_master_cv_text() or ""
    latest_cursor_prompt = str(getattr(request.app.state, "latest_cursor_prompt", "") or "")
    latest_tailored_cv = str(getattr(request.app.state, "latest_tailored_cv", "") or "")
    latest_tailored_cover = str(getattr(request.app.state, "latest_tailored_cover", "") or "")
    snap = monitor.snapshot()
    snap_json = json.dumps(snap, indent=2, sort_keys=True)
    kb_rows = [
        _kb_summary_fields(dict(r)) for r in storage.kb_list(limit=300, offset=0)
    ]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": jobs,
            "applications": applications,
            "kb_rows": kb_rows,
            "master_cv_prefill": master_cv_prefill,
            "latest_cursor_prompt": latest_cursor_prompt,
            "latest_tailored_cv": latest_tailored_cv,
            "latest_tailored_cover": latest_tailored_cover,
            "monitor_json": snap_json,
            "config_target_roles": settings.target_roles,
            "config_min_salary_gbp": settings.min_salary_gbp,
        },
    )


@app.post("/api/kb/add-text")
async def api_kb_add_text(
    content: str = Form(...),
    entry_type: str = Form("note"),
) -> JSONResponse:
    """Store a KB row from form fields ``content`` and optional ``entry_type``."""
    entry_id = storage.kb_insert(entry_type=entry_type or "note", content=content)
    return JSONResponse({"ok": True, "id": entry_id})


@app.post("/api/kb/upload")
async def api_kb_upload(file: UploadFile = File(...)) -> JSONResponse:
    """
    Save multipart upload under ``data/uploads`` and append extracted text as a KB entry.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty file")

    safe_name = Path(file.filename or "upload").name
    uid = uuid.uuid4().hex
    dest = _UPLOAD_DIR / f"{uid}_{safe_name}"
    dest.write_bytes(raw)

    try:
        text = extract_text_from_bytes(safe_name, raw).strip()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text:
        text = f"(no text extracted from {safe_name})"

    entry_id = storage.kb_insert(
        entry_type="upload",
        content=text,
        source_file=str(dest.relative_to(storage.DATA_DIR)),
    )
    return JSONResponse(
        {"ok": True, "id": entry_id, "stored_path": str(dest), "chars": len(text)}
    )


@app.get("/api/kb")
async def api_kb_list(
    limit: int = 200,
    offset: int = 0,
    entry_type: Optional[str] = None,
) -> JSONResponse:
    """
    List knowledge-base entries (newest first). Optional ``entry_type`` filter.
    """
    limit = min(max(limit, 1), 500)
    offset = max(offset, 0)
    rows = storage.kb_list(
        entry_type=entry_type, limit=limit, offset=offset
    )
    entries = [_kb_summary_fields(dict(r)) for r in rows]
    return JSONResponse({"ok": True, "entries": entries})


@app.get("/api/kb/{entry_id}")
async def api_kb_get(entry_id: int) -> JSONResponse:
    """Return one KB entry including full ``content``."""
    row = storage.kb_get_by_id(entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="KB entry not found")
    return JSONResponse({"ok": True, "entry": dict(row)})


@app.delete("/api/kb/{entry_id}")
async def api_kb_delete(entry_id: int) -> JSONResponse:
    """Delete a knowledge-base row by id."""
    if not storage.kb_delete(entry_id):
        raise HTTPException(status_code=404, detail="KB entry not found")
    return JSONResponse({"ok": True, "id": entry_id})


@app.post("/api/jobs/score")
async def api_jobs_score(
    request: Request, payload: Dict[str, Any] = Body(...)
) -> JSONResponse:
    """Enqueue ``score_jd`` and block up to 8s for the scoring result."""
    monitor: MonitorAgent = request.app.state.monitor
    settings: AppSettings = getattr(request.app.state, "settings", load_settings(_PROJECT_ROOT))
    jd_text = payload.get("jd_text")
    if jd_text is None:
        raise HTTPException(status_code=400, detail="jd_text required")
    target_roles = payload.get("target_roles")
    if target_roles is None or target_roles == []:
        target_roles = list(settings.target_roles)
    if not isinstance(target_roles, list):
        target_roles = [str(target_roles)]
    required_salary_gbp = payload.get("required_salary_gbp", settings.min_salary_gbp)

    task_id = monitor.enqueue(
        {
            "type": "score_jd",
            "payload": {
                "jd_text": jd_text,
                "target_roles": target_roles,
                "required_salary_gbp": required_salary_gbp,
            },
        }
    )
    status, rec = wait_for_task_terminal(monitor, task_id, 8.0)
    if status == "timeout":
        return JSONResponse(
            {"ok": False, "task_id": task_id, "timed_out": True},
            status_code=504,
        )
    assert rec is not None
    if rec.status == TaskStatus.FAILED:
        return JSONResponse(
            {"ok": False, "task_id": task_id, "error": rec.error},
            status_code=500,
        )
    return JSONResponse({"ok": True, "task_id": task_id, "result": rec.result})


@app.post("/api/jobs/tailor-prompt")
async def api_jobs_tailor_prompt(
    request: Request, payload: Dict[str, Any] = Body(...)
) -> JSONResponse:
    """
    Generate a Cursor-ready prompt for copy/paste workflow.
    """
    settings: AppSettings = getattr(request.app.state, "settings", load_settings(_PROJECT_ROOT))
    monitor: MonitorAgent = request.app.state.monitor
    jd_text = payload.get("jd_text")
    master_cv = payload.get("master_cv_markdown")
    if jd_text is None:
        raise HTTPException(status_code=400, detail="jd_text required")
    if not isinstance(master_cv, str) or not master_cv.strip():
        master_cv = latest_master_cv_text()
    if not isinstance(master_cv, str) or not master_cv.strip():
        raise HTTPException(
            status_code=400,
            detail="No master CV found. Upload your master CV first in 'Upload KB file'.",
        )

    cover_requested = bool(payload.get("cover_requested", False))

    highlights_raw = kb_highlights_latest(10)
    highlights = dedupe_kb_highlights(highlights_raw)
    highlights = filter_kb_highlights_vs_master_cv(highlights, master_cv)
    task_id = monitor.enqueue(
        {
            "type": "tailor_cv_prompt",
            "payload": {
                "jd_text": jd_text,
                "master_cv_markdown": master_cv,
                "kb_highlights": highlights,
                "cover_requested": cover_requested,
                "prompt_only": True,
                "locale_hint": settings.locale_hint,
            },
        }
    )
    status, rec = wait_for_task_terminal(monitor, task_id, 8.0)
    if status == "timeout":
        return JSONResponse(
            {"ok": False, "task_id": task_id, "timed_out": True},
            status_code=504,
        )
    assert rec is not None
    if rec.status == TaskStatus.FAILED:
        return JSONResponse(
            {"ok": False, "task_id": task_id, "error": rec.error},
            status_code=500,
        )
    result: Dict[str, Any] = dict(rec.result or {})
    base_prompt = str(result.get("prompt_markdown") or "")
    cursor_prompt = build_copy_paste_prompt(base_prompt, cover_requested=cover_requested)
    request.app.state.latest_cursor_prompt = cursor_prompt

    next_ingest = (
        "Paste this prompt into Cursor chat and paste its JSON response into "
        "/api/jobs/ingest-cursor-response with the same cover_requested value."
    )

    return JSONResponse(
        {
            "ok": True,
            "task_id": task_id,
            "cover_requested": cover_requested,
            "kb_entries_used": len(highlights_raw),
            "kb_entries_after_dedup": len(highlights),
            "workflow_mode": "copy-paste-cursor-chat",
            "prompt_markdown": cursor_prompt,
            "next_step": next_ingest,
            "result": {
                "prompt_markdown": cursor_prompt,
                "checklist": result.get("checklist", []),
            },
        }
    )


@app.post("/api/jobs/ingest-cursor-response")
async def api_jobs_ingest_cursor_response(
    request: Request, payload: Dict[str, Any] = Body(...)
) -> JSONResponse:
    """
    Ingest pasted Cursor chat response JSON and store latest tailored outputs in app state.
    """
    response_text = payload.get("response_text")
    if not isinstance(response_text, str) or not response_text.strip():
        raise HTTPException(status_code=400, detail="response_text required")
    cover_requested = bool(payload.get("cover_requested", False))
    try:
        parsed = parse_cursor_response_json(
            response_text, require_cover=cover_requested
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    request.app.state.latest_tailored_cv = parsed["tailored_cv_markdown"]
    request.app.state.latest_tailored_cover = parsed["tailored_cover_markdown"]
    return JSONResponse(
        {
            "ok": True,
            "cover_requested": cover_requested,
            "workflow_mode": "copy-paste-cursor-chat",
            "tailored_cv_markdown": parsed["tailored_cv_markdown"],
            "tailored_cover_markdown": parsed["tailored_cover_markdown"],
        }
    )


@app.post("/api/scrape/run")
async def api_scrape_run(
    request: Request, payload: Dict[str, Any] = Body(...)
) -> JSONResponse:
    """Enqueue ``scrape_jobs``, wait up to 25s, upsert scraped rows, return counts."""
    settings: AppSettings = getattr(request.app.state, "settings", load_settings(_PROJECT_ROOT))
    monitor: MonitorAgent = request.app.state.monitor
    urls = payload.get("urls") or []
    if not isinstance(urls, list):
        raise HTTPException(status_code=400, detail="urls must be a list")
    min_salary_gbp = payload.get("min_salary_gbp", settings.min_salary_gbp)

    task_id = monitor.enqueue(
        {
            "type": "scrape_jobs",
            "payload": {"urls": urls, "min_salary_gbp": min_salary_gbp},
        }
    )
    status, rec = wait_for_task_terminal(monitor, task_id, 25.0)
    if status == "timeout":
        return JSONResponse(
            {"ok": False, "task_id": task_id, "timed_out": True},
            status_code=504,
        )
    assert rec is not None
    if rec.status == TaskStatus.FAILED:
        return JSONResponse(
            {"ok": False, "task_id": task_id, "error": rec.error},
            status_code=500,
        )

    result = rec.result or {}
    listings = result.get("listings") or []
    inserted = updated = skipped = 0
    if isinstance(listings, list):
        for item in listings:
            if not isinstance(item, dict):
                skipped += 1
                continue
            op = upsert_job_listing(item)
            if op == "inserted":
                inserted += 1
            elif op == "updated":
                updated += 1
            else:
                skipped += 1

    return JSONResponse(
        {
            "ok": bool(result.get("ok", True)),
            "task_id": task_id,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "worker_result": result,
        }
    )


@app.post("/api/applications/add")
async def api_applications_add(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    """Insert an application row from JSON body fields."""
    required = ("company", "role", "link", "date_applied")
    for key in required:
        if key not in payload:
            raise HTTPException(status_code=400, detail=f"missing {key}")
    app_id = storage.application_insert(
        company=str(payload["company"]),
        role=str(payload["role"]),
        link=str(payload["link"]),
        date_applied=str(payload["date_applied"]),
        status=payload.get("status"),
        cv_version=payload.get("cv_version"),
        cover_version=payload.get("cover_version"),
        notes=payload.get("notes"),
    )
    return JSONResponse({"ok": True, "id": app_id})


@app.delete("/api/jobs/{job_id}")
async def api_jobs_delete(job_id: int) -> JSONResponse:
    """Delete one job listing row by id (scraped jobs board)."""
    if not storage.job_delete(job_id):
        raise HTTPException(status_code=404, detail="job not found")
    return JSONResponse({"ok": True, "id": job_id})


@app.post("/api/cv/export-pdf")
async def api_cv_export_pdf(payload: Dict[str, Any] = Body(...)) -> JSONResponse:
    """Export markdown/plain text to a local PDF in ``output/resumes``."""
    markdown_text = payload.get("markdown_text")
    output_name = payload.get("output_name")
    if not isinstance(markdown_text, str) or not markdown_text.strip():
        raise HTTPException(status_code=400, detail="markdown_text required")
    try:
        out_path = markdown_to_pdf(markdown_text, output_name=output_name)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "path": str(out_path)})


@app.get("/api/monitor")
async def api_monitor(request: Request) -> JSONResponse:
    """Return the current monitor queue/worker snapshot."""
    monitor: MonitorAgent = request.app.state.monitor
    return JSONResponse(monitor.snapshot())
