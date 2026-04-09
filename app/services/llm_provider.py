"""
OpenAI-compatible HTTP client for optional LLM-backed CV and cover letter tailoring.

Uses only the standard library and ``requests``. Configuration is read from
environment variables at construction time.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

# Env flag values treated as "on" for ``CURSOR_USE_LLM``.
_TRUTHY = frozenset({"1", "true", "yes", "on"})

# Default chat completion timeout (seconds) for slow providers.
_REQUEST_TIMEOUT_S = 90.0


def _env_truthy(raw: Optional[str]) -> bool:
    """Return True if ``raw`` is a common affirmative env value."""
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY


def _strip_json_fences(text: str) -> str:
    """
    Remove optional Markdown code fences from a model reply.

    Handles `` ```json ... ``` `` and plain `` ``` ... ``` ``.
    """
    s = text.strip()
    m = re.match(
        r"^```(?:json)?\s*\r?\n?(.*?)\r?\n?```\s*$",
        s,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()
    return s


def _infer_provider_label(base_url: str) -> str:
    """Short label for responses based on host (for ``provider`` field)."""
    low = base_url.lower()
    if "cursor.com" in low:
        return "cursor-openai-compatible"
    return "openai-compatible"


class TailorLLMProvider:
    """
    Call an OpenAI-compatible ``/chat/completions`` endpoint to produce tailored
    Markdown CV and cover letter from JD, master CV, and KB highlights.

    Enable with ``CURSOR_USE_LLM`` and set key, base URL, and optional model.
    """

    def __init__(self) -> None:
        """Read configuration from environment variables."""
        self._use_llm = _env_truthy(os.environ.get("CURSOR_USE_LLM"))
        self._api_key = (os.environ.get("CURSOR_API_KEY") or "").strip()
        self._base_url = (os.environ.get("CURSOR_OPENAI_BASE_URL") or "").strip().rstrip("/")
        model_raw = os.environ.get("CURSOR_MODEL")
        self._model = (model_raw.strip() if isinstance(model_raw, str) and model_raw.strip() else "gpt-4.1-mini")

    def is_enabled(self) -> bool:
        """
        Return True when the provider is allowed to call the remote API.

        Requires affirmative ``CURSOR_USE_LLM``, non-empty ``CURSOR_API_KEY``,
        and non-empty ``CURSOR_OPENAI_BASE_URL``.
        """
        if not self._use_llm:
            return False
        if not self._api_key:
            return False
        if not self._base_url:
            return False
        return True

    def generate(
        self,
        jd_text: str,
        master_cv_markdown: str,
        kb_highlights: List[str],
    ) -> Dict[str, Any]:
        """
        Request tailored Markdown documents from the configured endpoint.

        Args:
            jd_text: Full job description text.
            master_cv_markdown: Master CV in Markdown.
            kb_highlights: List of KB snippet strings (may be empty).

        Returns:
            Dict with ``tailored_cv_markdown``, ``tailored_cover_markdown``,
            ``provider`` (short label), and ``model`` (requested model id).

        Raises:
            ValueError: If disabled, HTTP/API errors, or JSON parsing/validation fails.
        """
        if not self.is_enabled():
            raise ValueError("LLM provider not enabled or missing CURSOR_API_KEY / CURSOR_OPENAI_BASE_URL")

        url = f"{self._base_url}/chat/completions"
        system_prompt = (
            "You are an assistant that tailors job application documents. "
            "Use only facts present in the job description, master CV, and KB highlights; "
            "do not invent employers, dates, metrics, or credentials. "
            "Respond with a single JSON object and no other text. "
            'The JSON must have exactly two string keys: "tailored_cv_markdown" and '
            '"tailored_cover_markdown". Values must be Markdown strings.'
        )
        user_payload = {
            "job_description": jd_text,
            "master_cv_markdown": master_cv_markdown,
            "kb_highlights": kb_highlights,
        }
        user_content = (
            "Produce the JSON object described in the system message from this input:\n"
            + json.dumps(user_payload, ensure_ascii=False)
        )
        body: Dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                url,
                headers=headers,
                data=json.dumps(body),
                timeout=_REQUEST_TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise ValueError(f"request failed: {exc}") from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            snippet = (resp.text or "")[:300].strip()
            raise ValueError(f"HTTP {resp.status_code}" + (f": {snippet}" if snippet else ""))

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise ValueError("response body is not valid JSON") from exc

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("missing or empty choices in API response")
        first = choices[0]
        if not isinstance(first, dict):
            raise ValueError("invalid choice object in API response")
        msg = first.get("message")
        if not isinstance(msg, dict):
            raise ValueError("missing message in API response")
        content = msg.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("empty assistant content in API response")

        raw_json = _strip_json_fences(content)
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"assistant output is not valid JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("parsed JSON must be an object")

        cv_key = "tailored_cv_markdown"
        cl_key = "tailored_cover_markdown"
        if cv_key not in parsed or cl_key not in parsed:
            raise ValueError(f"JSON must contain {cv_key!r} and {cl_key!r}")

        cv_md = parsed[cv_key]
        cl_md = parsed[cl_key]
        if not isinstance(cv_md, str) or not isinstance(cl_md, str):
            raise ValueError("tailored fields must be JSON strings")

        provider = _infer_provider_label(self._base_url)
        return {
            "tailored_cv_markdown": cv_md,
            "tailored_cover_markdown": cl_md,
            "provider": provider,
            "model": self._model,
        }
