"""v3.3 — explainer LLM calls with strict data minimization (spec 2.3).

Hard rules enforced here:
- Tier 1/2 use ``gpt-4o-mini``; Tier 3 chat uses ``gpt-4o``. Never gpt-4o for
  Tier 1/2 (cost control).
- Prompts contain ONLY the chart data being explained — never the full profile,
  and NEVER any PII (name, email). ``scrub_pii`` + ``assert_no_pii`` enforce
  this and back ``tests/test_data_minimization.py``.
- Strict system message; every response ends with the educational disclaimer.
"""
from __future__ import annotations

import json
import re
from typing import Any

# Reuse the existing key-resolution + graceful-degradation logic.
from modules import llm as base_llm


MODEL_TIER12 = "gpt-4o-mini"
MODEL_TIER3 = "gpt-4o"

SYSTEM_MESSAGE = (
    "You are a health data explainer. Do not provide medical advice. Do not "
    "invent values. If data is missing or uncertain, say so. Reference only the "
    "data provided."
)

DISCLAIMER = "Educational only — not medical advice. Discuss with your physician."

# Patterns that must never appear in an outbound prompt.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Keys that should be stripped from any data payload before it leaves the app.
_PII_KEYS = {"email", "name", "display_name", "first_name", "last_name",
             "full_name", "profile_id", "auth_email", "ip", "ip_hash",
             "address", "phone"}


def scrub_pii(data: Any) -> Any:
    """Recursively drop PII keys and redact any email-looking strings.

    Used on every payload before it is serialized into a prompt.
    """
    if isinstance(data, dict):
        return {k: scrub_pii(v) for k, v in data.items()
                if k.lower() not in _PII_KEYS}
    if isinstance(data, (list, tuple)):
        return [scrub_pii(v) for v in data]
    if isinstance(data, str):
        return _EMAIL_RE.sub("[redacted]", data)
    return data


def assert_no_pii(prompt: str, *, names: list[str] | None = None,
                  emails: list[str] | None = None) -> None:
    """Raise ``ValueError`` if the prompt contains any email or known PII.

    ``names``/``emails`` are the session's known identifiers to check against;
    an email regex catches anything else. This is the runtime guard behind the
    data-minimization test.
    """
    if _EMAIL_RE.search(prompt):
        raise ValueError("Prompt contains an email address — PII leak blocked.")
    for email in (emails or []):
        if email and email.lower() in prompt.lower():
            raise ValueError("Prompt contains a known user email — PII leak blocked.")
    for name in (names or []):
        if name and len(name) > 2 and name.lower() in prompt.lower():
            raise ValueError("Prompt contains a known user name — PII leak blocked.")


def build_prompt(template: str, data: Any) -> str:
    """Build a minimized prompt: a template + the scrubbed JSON payload."""
    clean = scrub_pii(data)
    return f"{template}\n\nDATA (JSON):\n{json.dumps(clean, default=str, sort_keys=True)}"


def _session_pii() -> tuple[list[str], list[str]]:
    """Pull the current session's name/email so we can assert they're absent."""
    try:
        import streamlit as st
        names = [st.session_state.get("display_name"), st.session_state.get("base_display_name")]
        emails = [st.session_state.get("auth_email")]
    except Exception:
        names, emails = [], []
    return [n for n in names if n], [e for e in emails if e]


def complete(prompt: str, *, model: str, max_tokens: int = 500,
             temperature: float = 0.3) -> tuple[str, dict[str, int]]:
    """Single completion. Returns (text, usage). Degrades to a placeholder when
    no API key is configured. Enforces PII-free prompts before sending."""
    names, emails = _session_pii()
    assert_no_pii(prompt, names=names, emails=emails)

    key = base_llm.get_api_key()
    if not key:
        return ("[LLM not configured — showing deterministic content only.]",
                {"prompt_tokens": 0, "completion_tokens": 0})
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        u = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
        }
        return text, u
    except Exception as e:  # noqa: BLE001
        return (f"[LLM call failed: {e}]", {"prompt_tokens": 0, "completion_tokens": 0})


def with_disclaimer(text: str) -> str:
    if DISCLAIMER in text:
        return text
    return f"{text.rstrip()}\n\n_{DISCLAIMER}_"
