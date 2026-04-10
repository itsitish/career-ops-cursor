"""
Load optional YAML profile from ``config/profile.yml`` (or ``profile.example.yml``).

Open-source users copy the example file and set target roles, salary floor, and notes
without editing Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

DEFAULT_MIN_SALARY_GBP = 60000


@dataclass
class AppSettings:
    """Runtime settings derived from ``config/profile*.yml``."""

    target_roles: List[str] = field(default_factory=list)
    min_salary_gbp: int = DEFAULT_MIN_SALARY_GBP
    """Minimum acceptable salary in GBP for JD scoring and scrape defaults."""
    sponsorship_note: str = ""
    """Free-text note for prompts (e.g. visa requirements)."""
    candidate_headline: str = ""
    """Optional one-line professional headline for tailor prompts."""
    locale_hint: str = "en-GB"
    """Spelling/locale hint passed into Cursor prompts (en-GB vs en-US)."""


def _as_str_list(val: Any) -> List[str]:
    if val is None:
        return []
    if isinstance(val, str) and val.strip():
        return [val.strip()]
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    return []


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    data = yaml.safe_load(raw)
    return data if isinstance(data, dict) else {}


def load_settings(project_root: Path) -> AppSettings:
    """
    Load ``config/profile.yml`` if present; otherwise ``config/profile.example.yml``.

    Missing files yield defaults suitable for a first clone.
    """
    config_dir = project_root / "config"
    user_path = config_dir / "profile.yml"
    example_path = config_dir / "profile.example.yml"
    path = user_path if user_path.is_file() else example_path
    data = _load_yaml(path)

    target_roles: List[str] = []
    tr = data.get("target_roles")
    if isinstance(tr, dict):
        target_roles.extend(_as_str_list(tr.get("primary")))
        arch = tr.get("archetypes")
        if isinstance(arch, list):
            for item in arch:
                if isinstance(item, dict) and item.get("name"):
                    target_roles.append(str(item["name"]).strip())
                elif isinstance(item, str):
                    target_roles.append(item.strip())
    elif isinstance(tr, list):
        target_roles = _as_str_list(tr)

    comp = data.get("compensation") if isinstance(data.get("compensation"), dict) else {}
    min_gbp = comp.get("minimum_gbp", comp.get("min_gbp", DEFAULT_MIN_SALARY_GBP))
    try:
        min_salary_gbp = int(min_gbp)
    except (TypeError, ValueError):
        min_salary_gbp = DEFAULT_MIN_SALARY_GBP

    loc = data.get("location") if isinstance(data.get("location"), dict) else {}
    sponsorship_note = str(loc.get("visa_sponsorship_note") or loc.get("visa_note") or "").strip()

    cand = data.get("candidate") if isinstance(data.get("candidate"), dict) else {}
    headline = str(cand.get("headline") or "").strip()

    locale_hint = str(data.get("locale") or data.get("locale_hint") or "en-GB").strip() or "en-GB"

    return AppSettings(
        target_roles=target_roles,
        min_salary_gbp=min_salary_gbp,
        sponsorship_note=sponsorship_note,
        candidate_headline=headline,
        locale_hint=locale_hint,
    )
