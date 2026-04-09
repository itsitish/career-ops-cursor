"""
Background-style worker that scrapes job listing pages heuristically.

Uses ``requests`` and ``BeautifulSoup``. Errors are captured per URL and per
card so a single failure never tears down the whole run.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Reasonable defaults for listing pages
_REQUEST_TIMEOUT_SEC = 25
_USER_AGENT = (
    "Mozilla/5.0 (compatible; CareerOpsScraper/1.0; +https://example.local)"
)

# Salary hints in class / text (weak signals for card boundaries)
_SALARY_CLASS_HINTS = re.compile(
    r"salary|compensation|pay|wage", re.I
)
_JOB_CONTAINER_HINTS = re.compile(
    r"job|listing|vacancy|position|opening|role|career|opp", re.I
)


def _task_type(task: Any) -> Optional[str]:
    """Extract task type from a mapping-like task object."""
    if not isinstance(task, dict):
        return None
    return (
        task.get("task_type")
        or task.get("type")
        or task.get("taskType")
    )


def _payload(task: dict[str, Any]) -> dict[str, Any]:
    """Normalize payload sub-dict from a task."""
    raw = task.get("payload")
    if isinstance(raw, dict):
        return raw
    return task


def _parse_gbp_amounts(text: str) -> list[int]:
    """
    Extract candidate annual GBP integers from free text.

    Handles ``£60,000``, ``60000``, ``£60k``, ``60k``, ``GBP 70k``.
    Returns all parsed values in **pounds** (not thousands).
    """
    if not text:
        return []
    found: list[int] = []
    # £12,345 or £12345
    for m in re.finditer(
        r"£\s*(\d{1,3}(?:,\d{3})+|\d{2,6})\b", text, re.I
    ):
        try:
            found.append(int(m.group(1).replace(",", "")))
        except ValueError:
            continue
    # 60k / £60k / GBP 60k
    for m in re.finditer(
        r"(?:£|\bGBP\s*)?\s*(\d{2,3})\s*k\b", text, re.I
    ):
        try:
            found.append(int(m.group(1)) * 1000)
        except ValueError:
            continue
    # Standalone large integers likely salary (avoid tiny numbers)
    for m in re.finditer(r"\b(\d{5,6})\b", text):
        try:
            n = int(m.group(1))
            if 20000 <= n <= 500000:
                found.append(n)
        except ValueError:
            continue
    return found


def max_parseable_salary_gbp(salary_text: Optional[str]) -> Optional[int]:
    """
    If ``salary_text`` yields at least one parseable GBP amount, return the max.

    Returns:
        Maximum parsed value, or ``None`` if nothing trustworthy was parsed.
    """
    if not salary_text:
        return None
    amounts = _parse_gbp_amounts(salary_text)
    return max(amounts) if amounts else None


def _should_filter_by_salary(
    salary_text: Optional[str], min_salary_gbp: int
) -> bool:
    """
    Return True if the listing should be dropped for being below ``min_salary_gbp``.

    Only filters when a salary is clearly parseable; ambiguous text is kept.
    """
    mx = max_parseable_salary_gbp(salary_text)
    if mx is None:
        return False
    return mx < min_salary_gbp


def _clean_text(el: Any, max_len: int = 8000) -> str:
    """Get stripped text from a BeautifulSoup node, bounded in length."""
    try:
        t = el.get_text(separator=" ", strip=True)
    except Exception:
        return ""
    if len(t) > max_len:
        return t[: max_len - 3] + "..."
    return t


def _class_str(classes: Any) -> str:
    if classes is None:
        return ""
    if isinstance(classes, str):
        return classes
    return " ".join(str(c) for c in classes)


def _is_probably_job_container(tag: Any) -> bool:
    """Heuristic: div/li/article whose class/id suggests a job row."""
    if tag.name not in ("article", "div", "li", "section", "tr"):
        return False
    blob = f"{_class_str(tag.get('class'))} {tag.get('id') or ''}"
    return bool(_JOB_CONTAINER_HINTS.search(blob))


def _find_salary_snippet(container: Any) -> Optional[str]:
    """Look for a short salary string inside a container."""
    # Elements whose class hints at salary
    for sub in container.find_all(True, class_=True):
        cls = _class_str(sub.get("class"))
        if _SALARY_CLASS_HINTS.search(cls):
            t = _clean_text(sub, 500)
            if t:
                return t
    # Fallback: any text chunk mentioning £ or k in salary-like context
    full = _clean_text(container, 4000)
    m = re.search(r"£[\d,\s]+(?:\s*-\s*£[\d,\s]+)?|\d{2,3}\s*k(?:\s*-\s*\d{2,3}\s*k)?", full, re.I)
    if m:
        return m.group(0).strip()
    return None


def _extract_cards(soup: BeautifulSoup) -> list[Any]:
    """Collect candidate DOM nodes that might each be one job listing."""
    seen_ids: set[int] = set()
    out: list[Any] = []

    def add(tag: Any) -> None:
        tid = id(tag)
        if tid not in seen_ids:
            seen_ids.add(tid)
            out.append(tag)

    for tag in soup.find_all(_is_probably_job_container):
        add(tag)

    # Generic fallback: any prominent job-board link blocks
    if not out:
        for a in soup.find_all("a", href=True):
            try:
                h = (a.get("href") or "").strip()
                if not h or h.startswith("#"):
                    continue
                title = _clean_text(a, 300)
                if len(title) < 8:
                    continue
                parent = a.find_parent(["article", "div", "li", "td"])
                if parent is not None:
                    add(parent)
                else:
                    add(a)
            except Exception:
                continue

    return out


def _normalize_listing(
    container: Any,
    base_url: str,
    page_source: str,
) -> Optional[dict[str, Any]]:
    """
    Build one normalized listing dict from a container element.

    Returns:
        Dict with keys company, role, link, salary_text, location, source,
        jd_text (optional), or None if no usable link/title.
    """
    try:
        link_el = container.find("a", href=True)
        if link_el is None and container.name == "a" and container.get("href"):
            link_el = container
        if link_el is None:
            return None

        href = (link_el.get("href") or "").strip()
        if not href or href.startswith("#") or href.lower().startswith("javascript:"):
            return None

        absolute = urljoin(base_url, href)
        role = _clean_text(link_el, 400) or "Unknown role"

        company = ""
        # Often a second line or sibling
        for sel in ["[class*='company']", "[class*='employer']", "h2", "h3", "span"]:
            node = container.select_one(sel)
            if node and node is not link_el:
                t = _clean_text(node, 200)
                if t and t != role:
                    company = t
                    break

        salary_text = _find_salary_snippet(container)
        location = ""
        for sel in ["[class*='location']", "[class*='place']", "[class*='city']"]:
            node = container.select_one(sel)
            if node:
                location = _clean_text(node, 200)
                if location:
                    break

        jd_text: Optional[str] = None
        desc = container.find(["p", "div"], class_=re.compile(r"desc|summary|snippet", re.I))
        if desc:
            jd_text = _clean_text(desc, 4000) or None

        parsed = urlparse(base_url)
        source = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else page_source

        return {
            "company": company or "",
            "role": role,
            "link": absolute,
            "salary_text": salary_text,
            "location": location,
            "source": source,
            "jd_text": jd_text,
        }
    except Exception:
        return None


class ScraperWorker:
    """
    Worker that handles ``scrape_jobs`` tasks by fetching URLs and parsing HTML.

    Attributes:
        worker_id: Stable id for logging or routing.
    """

    worker_id: str = "scraper_worker"

    def can_handle(self, task_type: str) -> bool:
        """
        Return True if this worker supports the given ``task_type``.

        Args:
            task_type: Logical task name (e.g. ``\"scrape_jobs\"``).
        """
        return task_type == "scrape_jobs"

    def process(self, task: Any) -> dict[str, Any]:
        """
        Run scraping for a single task.

        Expected task shape (flexible keys):
            - ``task_type`` / ``type``: ``\"scrape_jobs\"``
            - ``payload`` or top-level: ``urls`` (list of str),
              ``min_salary_gbp`` (int, default 60000).

        Returns:
            Result dict with ``ok``, ``worker_id``, ``listings``, ``errors``,
            and per-URL summaries. Never raises for normal input failures.
        """
        errors: list[dict[str, Any]] = []
        listings: list[dict[str, Any]] = []
        url_results: list[dict[str, Any]] = []

        try:
            if not isinstance(task, dict):
                return {
                    "ok": False,
                    "worker_id": self.worker_id,
                    "listings": [],
                    "errors": [{"stage": "validate", "message": "task must be a dict"}],
                    "url_results": [],
                }

            ttype = _task_type(task)
            if ttype != "scrape_jobs":
                return {
                    "ok": False,
                    "worker_id": self.worker_id,
                    "listings": [],
                    "errors": [
                        {
                            "stage": "validate",
                            "message": f"unsupported task_type: {ttype!r}",
                        }
                    ],
                    "url_results": [],
                }

            payload = _payload(task)
            urls_raw = payload.get("urls", [])
            if not isinstance(urls_raw, list):
                errors.append(
                    {"stage": "validate", "message": "payload.urls must be a list"}
                )
                urls: list[str] = []
            else:
                urls = [str(u).strip() for u in urls_raw if str(u).strip()]

            try:
                min_salary = int(payload.get("min_salary_gbp", 60000))
            except (TypeError, ValueError):
                min_salary = 60000
                errors.append(
                    {
                        "stage": "validate",
                        "message": "min_salary_gbp invalid; using 60000",
                    }
                )

            session = requests.Session()
            session.headers.update({"User-Agent": _USER_AGENT})

            for url in urls:
                page_listings: list[dict[str, Any]] = []
                page_errors: list[dict[str, Any]] = []
                try:
                    resp = session.get(url, timeout=_REQUEST_TIMEOUT_SEC)
                    resp.raise_for_status()
                    ctype = (resp.headers.get("content-type") or "").lower()
                    if "html" not in ctype and "text" not in ctype:
                        page_errors.append(
                            {
                                "url": url,
                                "message": f"skip non-html content-type: {ctype!r}",
                            }
                        )
                    else:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        cards = _extract_cards(soup)
                        seen_links: set[str] = set()
                        for card in cards:
                            try:
                                norm = _normalize_listing(
                                    card, base_url=url, page_source=url
                                )
                                if not norm:
                                    continue
                                lk = norm.get("link") or ""
                                if lk in seen_links:
                                    continue
                                seen_links.add(lk)

                                sal = norm.get("salary_text")
                                if _should_filter_by_salary(sal, min_salary):
                                    continue

                                listings.append(norm)
                                page_listings.append(norm)
                            except Exception as ex:
                                page_errors.append(
                                    {
                                        "url": url,
                                        "message": f"card parse: {str(ex)}",
                                    }
                                )
                except requests.RequestException as ex:
                    page_errors.append({"url": url, "message": str(ex)})
                except Exception as ex:
                    page_errors.append({"url": url, "message": f"unexpected: {str(ex)}"})

                errors.extend(page_errors)
                url_results.append(
                    {
                        "url": url,
                        "count": len(page_listings),
                        "errors": page_errors,
                    }
                )

            return {
                "ok": True,
                "worker_id": self.worker_id,
                "listings": listings,
                "errors": errors,
                "url_results": url_results,
                "min_salary_gbp": min_salary,
            }
        except Exception as ex:
            # Final guard — worker must not crash the caller
            return {
                "ok": False,
                "worker_id": self.worker_id,
                "listings": listings,
                "errors": errors
                + [{"stage": "fatal", "message": str(ex)}],
                "url_results": url_results,
            }
