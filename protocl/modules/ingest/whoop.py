"""Whoop ingest scaffold.

Whoop publishes a developer API behind OAuth2. This scaffold exposes:

    is_configured() -> bool
    pull_recovery(start: date, end: date) -> pd.DataFrame    # → wearables schema
    pull_workouts(start: date, end: date) -> pd.DataFrame    # → training schema

Auth flow is OAuth2 authorization-code with PKCE. The expected secrets:

    WHOOP_CLIENT_ID
    WHOOP_CLIENT_SECRET
    WHOOP_REFRESH_TOKEN     # obtained once via the OAuth flow

The actual HTTP calls are stubbed — flip the `_LIVE` flag to True once the
secrets are wired up and the OAuth dance has been run once.
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
_API_BASE = "https://api.prod.whoop.com/developer/v1"


def _secret(key: str) -> Optional[str]:
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.environ.get(key)


def is_configured() -> bool:
    return bool(_secret("WHOOP_CLIENT_ID")
                and _secret("WHOOP_CLIENT_SECRET")
                and _secret("WHOOP_REFRESH_TOKEN"))


def _refresh_access_token() -> Optional[str]:
    """Exchange the long-lived refresh token for a short-lived access token."""
    if not is_configured() or not _LIVE:
        return None
    try:
        import requests
        r = requests.post(
            "https://api.prod.whoop.com/oauth/oauth2/token",
            data={
                "grant_type":    "refresh_token",
                "refresh_token": _secret("WHOOP_REFRESH_TOKEN"),
                "client_id":     _secret("WHOOP_CLIENT_ID"),
                "client_secret": _secret("WHOOP_CLIENT_SECRET"),
                "scope":         "offline read:recovery read:sleep read:workout read:cycles",
            }, timeout=20,
        )
        if r.status_code != 200:
            return None
        return r.json().get("access_token")
    except Exception:
        return None


def pull_recovery(start: date, end: date) -> pd.DataFrame:
    """Pull recovery scores in `wearables` schema. Returns empty DF when stubbed."""
    if not _LIVE or not is_configured():
        return pd.DataFrame(columns=[
            "date", "resting_hr_bpm", "hrv_sdnn_ms", "sleep_duration_hrs",
            "respiratory_rate_brpm", "source",
        ])
    # — live path (will be filled in once OAuth dance is verified) —
    token = _refresh_access_token()
    if not token:
        return pd.DataFrame()
    import requests
    r = requests.get(
        f"{_API_BASE}/recovery",
        headers={"Authorization": f"Bearer {token}"},
        params={"start": start.isoformat(), "end": end.isoformat()},
        timeout=30,
    )
    if r.status_code != 200:
        return pd.DataFrame()
    rows = []
    for item in r.json().get("records", []):
        score = item.get("score", {})
        rows.append({
            "date": item.get("created_at", "")[:10],
            "resting_hr_bpm": score.get("resting_heart_rate"),
            "hrv_sdnn_ms":    score.get("hrv_rmssd_milli"),
            "sleep_duration_hrs": (item.get("sleep", {}).get("score", {}) or {}).get(
                "total_in_bed_time_milli", 0) / 3_600_000,
            "respiratory_rate_brpm": score.get("respiratory_rate"),
            "source": "whoop",
        })
    return pd.DataFrame(rows)


def pull_workouts(start: date, end: date) -> pd.DataFrame:
    """Pull workouts in `training` schema. Returns empty DF when stubbed."""
    if not _LIVE or not is_configured():
        return pd.DataFrame(columns=[
            "date", "activity_type", "source", "duration_min",
            "avg_hr_bpm", "max_hr_bpm", "calories", "tss",
        ])
    # — live path stub —
    return pd.DataFrame()
