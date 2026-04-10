"""
Cursor Cloud Agent API provider for tailored CV/Cover generation.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_truthy(raw: Optional[str]) -> bool:
    """Return True if env value is affirmative."""
    return bool(raw and raw.strip().lower() in _TRUTHY)


def _strip_json_fences(text: str) -> str:
    """Remove optional fenced code wrapper around JSON."""
    s = text.strip()
    m = re.match(r"^```(?:json)?\s*\r?\n?(.*?)\r?\n?```\s*$", s, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else s


class CursorCloudAgentProvider:
    """
    Use Cursor Cloud Agents API to generate tailored markdown outputs.

    Required config:
    - CURSOR_USE_CLOUD_AGENT=1
    - CURSOR_API_KEY
    - CURSOR_SOURCE_REPOSITORY
    Optional:
    - CURSOR_API_BASE (default https://api.cursor.com)
    - CURSOR_SOURCE_REF
    - CURSOR_AGENT_MODEL (fallback: CURSOR_PINNED_MODEL)
    - CURSOR_AGENT_TIMEOUT_S (default 180)
    """

    def __init__(self) -> None:
        self._enabled = _env_truthy(os.environ.get("CURSOR_USE_CLOUD_AGENT"))
        self._api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
        self._api_base = (os.environ.get("CURSOR_API_BASE") or "https://api.cursor.com").strip().rstrip("/")
        self._repo = (os.environ.get("CURSOR_SOURCE_REPOSITORY") or "").strip()
        self._ref = (os.environ.get("CURSOR_SOURCE_REF") or "").strip()
        model_raw = (os.environ.get("CURSOR_AGENT_MODEL") or os.environ.get("CURSOR_PINNED_MODEL") or "").strip()
        self._model = model_raw or "claude-sonnet-4-6"
        timeout_raw = (os.environ.get("CURSOR_AGENT_TIMEOUT_S") or "").strip()
        try:
            self._timeout_s = max(30, int(timeout_raw)) if timeout_raw else 180
        except ValueError:
            self._timeout_s = 180

    def is_enabled(self) -> bool:
        """True when required config is present."""
        return bool(self._enabled and self._api_key and self._repo)

    def generate(self, jd_text: str, master_cv_markdown: str, kb_highlights: List[str]) -> Dict[str, Any]:
        """
        Launch a cloud agent, wait for completion, and parse JSON output.
        """
        if not self.is_enabled():
            raise ValueError("cloud agent provider not enabled or missing CURSOR_API_KEY/CURSOR_SOURCE_REPOSITORY")

        prompt_text = self._build_prompt(jd_text, master_cv_markdown, kb_highlights)
        launch_payload: Dict[str, Any] = {
            "prompt": {"text": prompt_text},
            "source": {"repository": self._repo},
            "model": self._model,
        }
        if self._ref:
            launch_payload["source"]["ref"] = self._ref

        launched = self._request_json("POST", "/v0/agents", json_payload=launch_payload)
        agent_id = self._extract_agent_id(launched)
        if not agent_id:
            raise ValueError("could not read agent id from Cursor API response")

        self._wait_until_done(agent_id)
        convo = self._request_json("GET", f"/v0/agents/{agent_id}/conversation")
        assistant_text = self._extract_assistant_text(convo)
        if not assistant_text:
            raise ValueError("no assistant output found in cloud agent conversation")

        parsed = self._parse_agent_json(assistant_text)
        return {
            "tailored_cv_markdown": parsed["tailored_cv_markdown"],
            "tailored_cover_markdown": parsed["tailored_cover_markdown"],
            "provider": "cursor-cloud-agent",
            "model": self._model,
            "agent_id": agent_id,
        }

    def _request_json(self, method: str, path: str, json_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Make one JSON request against Cursor API."""
        url = f"{self._api_base}{path}"
        try:
            resp = requests.request(
                method=method,
                url=url,
                json=json_payload,
                auth=HTTPBasicAuth(self._api_key, ""),
                timeout=45,
            )
        except requests.RequestException as exc:
            raise ValueError(f"Cursor API request failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            snippet = (resp.text or "")[:300].strip()
            raise ValueError(f"Cursor API HTTP {resp.status_code}" + (f": {snippet}" if snippet else ""))
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise ValueError("Cursor API response was not JSON") from exc

    def _extract_agent_id(self, payload: Dict[str, Any]) -> Optional[str]:
        """Best-effort extraction of agent id from launch response."""
        direct = payload.get("id")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        agent = payload.get("agent")
        if isinstance(agent, dict):
            aid = agent.get("id")
            if isinstance(aid, str) and aid.strip():
                return aid.strip()
        return None

    def _read_status(self, payload: Dict[str, Any]) -> Optional[str]:
        """Extract agent status from possible response shapes."""
        s = payload.get("status")
        if isinstance(s, str):
            return s.upper()
        a = payload.get("agent")
        if isinstance(a, dict):
            s2 = a.get("status")
            if isinstance(s2, str):
                return s2.upper()
        return None

    def _wait_until_done(self, agent_id: str) -> None:
        """Poll agent status until terminal state or timeout."""
        deadline = time.monotonic() + self._timeout_s
        terminal = {"FINISHED", "FAILED", "CANCELLED"}
        while time.monotonic() < deadline:
            state = self._request_json("GET", f"/v0/agents/{agent_id}")
            status = self._read_status(state)
            if status in terminal:
                if status != "FINISHED":
                    raise ValueError(f"cloud agent ended with status {status}")
                return
            time.sleep(2.0)
        raise ValueError(f"cloud agent timed out after {self._timeout_s}s")

    def _extract_assistant_text(self, payload: Dict[str, Any]) -> str:
        """Extract latest assistant message text from conversation payload."""
        seq = None
        for key in ("messages", "conversation", "items"):
            if isinstance(payload.get(key), list):
                seq = payload[key]
                break
        if not isinstance(seq, list):
            return ""

        for item in reversed(seq):
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").lower()
            if role and role != "assistant":
                continue

            content = item.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: List[str] = []
                for c in content:
                    if isinstance(c, dict):
                        txt = c.get("text")
                        if isinstance(txt, str) and txt.strip():
                            parts.append(txt.strip())
                if parts:
                    return "\n".join(parts).strip()
        return ""

    def _parse_agent_json(self, text: str) -> Dict[str, str]:
        """Parse strict JSON output from agent text."""
        raw = _strip_json_fences(text)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"agent output was not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("agent output JSON must be an object")
        cv = parsed.get("tailored_cv_markdown")
        cover = parsed.get("tailored_cover_markdown")
        if not isinstance(cv, str) or not isinstance(cover, str):
            raise ValueError("agent output missing tailored_cv_markdown/tailored_cover_markdown strings")
        return {
            "tailored_cv_markdown": cv,
            "tailored_cover_markdown": cover,
        }

    def _build_prompt(self, jd_text: str, master_cv_markdown: str, kb_highlights: List[str]) -> str:
        """Prompt instructing strict JSON output from cloud agent."""
        payload = {
            "job_description": jd_text,
            "master_cv_markdown": master_cv_markdown,
            "kb_highlights": kb_highlights,
        }
        return (
            "Generate a tailored CV and cover letter using ONLY provided facts. "
            "Do not invent employers, dates, metrics, or skills.\n"
            "Return JSON only, with exactly these keys:\n"
            "{\n"
            '  "tailored_cv_markdown": "...",\n'
            '  "tailored_cover_markdown": "..."\n'
            "}\n"
            "Use markdown strings for both values.\n\n"
            "Input:\n"
            + json.dumps(payload, ensure_ascii=False)
        )
