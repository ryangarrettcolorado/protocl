"""Shared time-range selector with per-page persistence.

Pages use ``render_time_range_selector(page_id)`` to drop a preset/custom
range picker into the UI and then ``filter_by_range(df, "date_col", ...)``
to apply the selection. The chosen preset (and any custom dates) persist
per page via the existing `preferences.py` JSON store.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from modules.preferences import load_preferences, save_preferences


# Anchor "today" matches the demo timestamp used elsewhere in the codebase.
TODAY = pd.Timestamp("2026-05-25")

PRESETS: list[tuple[str, str]] = [
    ("7d",   "Last 7 days"),
    ("30d",  "Last 30 days"),
    ("90d",  "Last 90 days"),
    ("6mo",  "Last 6 months"),
    ("1yr",  "Last 1 year"),
    ("all",  "All time"),
    ("custom", "Custom range…"),
]

_PRESET_DAYS = {"7d": 7, "30d": 30, "90d": 90, "6mo": 183, "1yr": 365}


def _state_for(prefs: dict[str, Any], page_id: str) -> dict[str, Any]:
    return ((prefs.get("time_ranges") or {}).get(page_id) or {})


def _save_state(page_id: str, state: dict[str, Any]) -> None:
    prefs = load_preferences()
    prefs.setdefault("time_ranges", {})
    prefs["time_ranges"][page_id] = state
    save_preferences(prefs)


def resolve_range(preset: str, custom_start: date | None = None,
                  custom_end: date | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Translate a preset id (and optional custom dates) to a (start, end) pair."""
    end = TODAY
    if preset == "custom" and custom_start and custom_end:
        return pd.Timestamp(custom_start), pd.Timestamp(custom_end)
    if preset == "all":
        return pd.Timestamp("1970-01-01"), end
    days = _PRESET_DAYS.get(preset, 90)
    return end - pd.Timedelta(days=days), end


def render_time_range_selector(
    page_id: str,
    *,
    default_preset: str = "90d",
    label: str = "Time range",
    key_prefix: str | None = None,
) -> tuple[pd.Timestamp, pd.Timestamp, str]:
    """Render the preset+custom picker for `page_id` and return (start, end, preset_id).

    Persists the selection back to ``user_preferences.json`` under
    ``time_ranges.<page_id>`` so it survives reruns and reloads.
    """
    prefs = load_preferences()
    saved = _state_for(prefs, page_id)
    preset = saved.get("preset", default_preset)
    if preset not in {p for p, _ in PRESETS}:
        preset = default_preset

    key_p = f"{key_prefix or page_id}_tr_preset"
    key_s = f"{key_prefix or page_id}_tr_start"
    key_e = f"{key_prefix or page_id}_tr_end"

    labels = [lbl for _, lbl in PRESETS]
    ids = [pid for pid, _ in PRESETS]
    idx = ids.index(preset) if preset in ids else ids.index(default_preset)

    col_a, col_b = st.columns([2, 3])
    with col_a:
        choice = st.selectbox(label, labels, index=idx, key=key_p)
    chosen = ids[labels.index(choice)]

    custom_start = saved.get("start")
    custom_end = saved.get("end")
    if custom_start:
        try: custom_start = pd.Timestamp(custom_start).date()
        except Exception: custom_start = None
    if custom_end:
        try: custom_end = pd.Timestamp(custom_end).date()
        except Exception: custom_end = None

    if chosen == "custom":
        with col_b:
            today_d = TODAY.date()
            cs = custom_start or (today_d - timedelta(days=90))
            ce = custom_end or today_d
            dr = st.date_input("Custom range", value=(cs, ce),
                                key=f"{key_prefix or page_id}_tr_custom")
            if isinstance(dr, tuple) and len(dr) == 2:
                custom_start, custom_end = dr
            else:
                custom_start, custom_end = cs, ce

    start, end = resolve_range(chosen, custom_start, custom_end)

    # Persist only on change to keep writes cheap.
    new_state = {"preset": chosen}
    if chosen == "custom":
        new_state["start"] = str(custom_start)
        new_state["end"] = str(custom_end)
    if new_state != saved:
        _save_state(page_id, new_state)

    return start, end, chosen


def filter_by_range(df: pd.DataFrame, date_col: str,
                    start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Return rows whose `date_col` falls within [start, end] inclusive."""
    if df is None or df.empty or date_col not in df.columns:
        return df
    col = pd.to_datetime(df[date_col], errors="coerce")
    mask = (col >= start) & (col <= end)
    return df[mask].copy()
