"""Optional LLM hookup — degrades gracefully when no API key is configured.

Looks up an OpenAI API key from `st.secrets["OPENAI_API_KEY"]` or the env var
`OPENAI_API_KEY`. If neither is present, returns a clear placeholder so the
rest of the app continues to function.

Drop a real key into `.streamlit/secrets.toml`:

    OPENAI_API_KEY = "sk-..."
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
    """
    key = get_api_key()
    if not key:
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
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"[LLM call failed: {e}]"


def llm_badge() -> str:
    """Tiny HTML badge to indicate LLM live vs demo mode."""
    if is_configured():
        return (
            '<span style="background:rgba(76,175,80,0.18);'
            'color:#4CAF50;padding:2px 8px;border-radius:4px;'
            'font-size:0.75rem;font-weight:600;">LLM LIVE</span>'
        )
    return (
        '<span style="background:rgba(255,152,0,0.18);'
        'color:#FF9800;padding:2px 8px;border-radius:4px;'
        'font-size:0.75rem;font-weight:600;">DEMO MODE</span>'
    )
