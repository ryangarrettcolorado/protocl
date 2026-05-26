"""Oura ingest scaffold.

Oura's Cloud API v2 is simpler than Whoop — it accepts a long-lived Personal
Access Token (no OAuth dance required). Get one from
https://cloud.ouraring.com/personal-access-tokens.

Wire it as:

    OURA_PAT = "..."

The token is sent as a bearer header on every request. Live calls are gated by
the `_LIVE` flag; flip it on once you've populated the secret and confirmed
one round-trip works.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import pandas as pd

try:
    import streamlit as st
except ImportError:
    st = None  # type: ignore


_LIVE = False
_API_BASE = "https://api.ouraring.com/v2/usercollection"


def _secret(key: str) -> Optional[str]:
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.environ.get(key)


def is_configured() -> bool:
    return bool(_secret("OURA_PAT"))


def _headers() -> dict:
    return {"Authorization": f"Bearer {_secret('OURA_PAT')}"}


def pull_daily_summary(start: date, end: date) -> pd.DataFrame:
    """Pull daily sleep + readiness summaries in `wearables` schema."""
    cols = ["date", "resting_hr_bpm", "hrv_sdnn_ms", "sleep_duration_hrs",
            "sleep_deep_hrs", "sleep_rem_hrs", "respiratory_rate_brpm", "source"]
    if not _LIVE or not is_configured():
        return pd.DataFrame(columns=cols)
    try:
        import requests
    except ImportError:
        return pd.DataFrame(columns=cols)

    # Sleep endpoint
    r_sleep = requests.get(
        f"{_API_BASE}/daily_sleep",
        headers=_headers(),
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        timeout=30,
    )
    if r_sleep.status_code != 200:
        return pd.DataFrame(columns=cols)

    # Readiness endpoint (heart-rate metrics)
    r_ready = requests.get(
        f"{_API_BASE}/daily_readiness",
        headers=_headers(),
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        timeout=30,
    )

    sleep_rows  = {d["day"]: d for d in r_sleep.json().get("data", [])}
    ready_rows  = {d["day"]: d for d in (r_ready.json().get("data", []) if r_ready.ok else [])}

    out = []
    for day, s in sleep_rows.items():
        c = s.get("contributors", {}) or {}
        r = ready_rows.get(day, {}).get("contributors", {}) or {}
        out.append({
            "date": day,
            "resting_hr_bpm":        r.get("resting_heart_rate"),
            "hrv_sdnn_ms":           r.get("hrv_balance"),
            "sleep_duration_hrs":    (c.get("total_sleep", 0) or 0) / 60.0,
            "sleep_deep_hrs":        (c.get("deep_sleep", 0) or 0) / 60.0,
            "sleep_rem_hrs":         (c.get("rem_sleep", 0) or 0) / 60.0,
            "respiratory_rate_brpm": r.get("respiratory_rate"),
            "source": "oura",
        })
    return pd.DataFrame(out, columns=cols)
