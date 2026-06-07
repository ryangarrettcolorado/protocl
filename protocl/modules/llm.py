"""Optional LLM hookup — degrades gracefully when no API key is configured.

Looks up an OpenAI API key from `st.secrets["OPENAI_API_KEY"]` or the env var
`OPENAI_API_KEY`. If neither is present, the app continues in demo mode and
shows deterministic rule-based output.

Drop a real key into `.streamlit/secrets.toml`:

    OPENAI_API_KEY = "sk-..."

The module exposes:
- ``is_configured()`` — has any key been provided
- ``llm_chat(prompt, ...)`` — single-shot completion with discriminated error
  states (each failure tags ``st.session_state["llm_last_status"]`` so the
  status badge can reflect the most recent call's outcome).
- ``llm_badge()`` — small HTML chip: LLM LIVE / LLM KEY MISSING / LLM BILLING
  / QUOTA ISSUE / LLM ERROR / DEMO MODE.
"""
from __future__ import annotations

import os
from typing import Optional

import streamlit as st


SYSTEM_DEFAULT = (
    "You are a longevity-focused clinical reasoning assistant for a personal "
    "health intelligence dashboard. You write tightly, cite specific numbers "
    "from the user's data, and you never invent biomarker values. When data "
    "is missing, you say so. You write for an expert user comfortable with "
    "PhenoAge, ApoB, hsCRP, HOMA-IR, Z2 dose, and N=1 design."
)


# Status keys — written into st.session_state["llm_last_status"]
STATUS_LIVE         = "live"           # successful call
STATUS_KEY_MISSING  = "key_missing"    # no key configured
STATUS_BILLING      = "billing"        # 401 / 403 / invalid_request_error w/ billing
STATUS_QUOTA        = "quota"          # 429 / insufficient_quota
STATUS_ERROR        = "error"          # other failures (network, model, etc.)
STATUS_IDLE         = "idle"           # configured but no call yet this session


def _set_status(status: str) -> None:
    try:
        st.session_state["llm_last_status"] = status
    except Exception:
        # Safe to ignore outside Streamlit script context
        pass


def get_api_key() -> Optional[str]:
    """Pull the OpenAI key from st.secrets, then fall back to env var."""
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


def is_configured() -> bool:
    """True when an API key is available."""
    return bool(get_api_key())


def _classify_error(exc: Exception) -> str:
    """Map an OpenAI / network exception to one of our discriminated statuses."""
    msg = str(exc).lower()
    # OpenAI SDK exposes status_code on http errors
    code = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
    if code == 429 or "insufficient_quota" in msg or "rate limit" in msg or "quota" in msg:
        return STATUS_QUOTA
    if code in (401, 403) or "invalid_api_key" in msg or "incorrect api key" in msg \
            or "billing" in msg or "payment" in msg:
        return STATUS_BILLING
    return STATUS_ERROR


@st.cache_data(ttl=600, show_spinner=False)
def llm_chat(
    prompt: str,
    *,
    system: str = SYSTEM_DEFAULT,
    model: str = "gpt-4o-mini",
    max_tokens: int = 700,
    temperature: float = 0.3,
) -> str:
    """Single-shot completion. Cached to avoid burning tokens on rerenders.

    Returns a plain-text response. If the LLM is not configured, returns a
    bracketed placeholder so the page still renders cleanly in demo mode.
    The most recent call's outcome is recorded in
    ``st.session_state["llm_last_status"]`` so :func:`llm_badge` can
    discriminate between the failure modes.
    """
    key = get_api_key()
    if not key:
        _set_status(STATUS_KEY_MISSING)
        return (
            "[LLM not configured — set OPENAI_API_KEY in .streamlit/secrets.toml. "
            "In demo mode, Protocōl shows deterministic rule-based output instead.]"
        )
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        _set_status(STATUS_LIVE)
        return resp.choices[0].message.content or ""
    except Exception as e:
        status = _classify_error(e)
        _set_status(status)
        if status == STATUS_QUOTA:
            return ("[LLM quota exceeded — your OpenAI account hit its rate or token "
                    f"limit. Try again later, or check usage at platform.openai.com. (detail: {e})]")
        if status == STATUS_BILLING:
            return ("[LLM billing / authentication issue — the API key was rejected or "
                    f"your account has no available billing. (detail: {e})]")
        return f"[LLM call failed: {e}]"


def llm_status() -> str:
    """Return the current status string (one of the STATUS_* constants).

    Reads from session state first (most recent call), falls back to a
    config-only check.
    """
    try:
        s = st.session_state.get("llm_last_status")
    except Exception:
        s = None
    if s:
        return s
    return STATUS_IDLE if is_configured() else STATUS_KEY_MISSING


# Visual tokens for each status — kept as a single block so it's easy to edit.
# Visual tokens are now mode-aware: each badge uses CSS variables so
# light/dark theming swap automatically via the body[data-theme] selector.
_BADGE_STYLES = {
    STATUS_LIVE:        ("LLM LIVE",        "var(--brand-success-soft)", "var(--brand-success)"),
    STATUS_IDLE:        ("LLM LIVE",        "var(--brand-success-soft)", "var(--brand-success)"),
    STATUS_KEY_MISSING: ("LLM KEY MISSING", "var(--brand-warn-soft)",    "var(--brand-warn)"),
    STATUS_BILLING:     ("LLM BILLING",     "var(--brand-danger-soft)",  "var(--brand-danger)"),
    STATUS_QUOTA:       ("QUOTA ISSUE",     "var(--brand-danger-soft)",  "var(--brand-danger)"),
    STATUS_ERROR:       ("LLM ERROR",       "var(--brand-danger-soft)",  "var(--brand-danger)"),
}


def llm_badge() -> str:
    """Tiny HTML badge reflecting the most recent LLM call (or current config)."""
    status = llm_status()
    label, bg, color = _BADGE_STYLES.get(status, _BADGE_STYLES[STATUS_ERROR])
    return (
        f'<span style="background:{bg};color:{color};padding:2px 8px;'
        f'border-radius:4px;font-size:0.75rem;font-weight:600;">{label}</span>'
    )
