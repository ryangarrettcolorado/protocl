"""Centralized CSV / JSON loading with Streamlit caching.

All page modules should import `load_data()` and `refresh_data()` from here
rather than calling pandas directly — that way every data source flows
through the same cache and refresh path.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# Default user id — Phase 1 ships single-tenant but the data layer is keyed
# by user so multi-user is a drop-in change later.
DEFAULT_USER = "ryan"


def _user_dir(user_id: str = DEFAULT_USER) -> Path:
    """Per-user directory inside data/. Falls back to data/ if user dir is absent."""
    p = DATA_DIR / user_id
    return p if p.exists() else DATA_DIR


def _read_csv(name: str, user_id: str = DEFAULT_USER, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = _user_dir(user_id) / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if parse_dates:
        for col in parse_dates:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _read_json(name: str, user_id: str = DEFAULT_USER) -> Any:
    path = _user_dir(user_id) / name
    if not path.exists():
        return []
    with path.open() as f:
        return json.load(f)


@dataclass
class HealthData:
    """Container for every cached DataFrame.

    Pages destructure what they need. New tables are additive — add a field
    here and load it in `load_data` below.
    """
    bloodwork:        pd.DataFrame = field(default_factory=pd.DataFrame)
    protocol:         pd.DataFrame = field(default_factory=pd.DataFrame)
    inbody:           pd.DataFrame = field(default_factory=pd.DataFrame)
    training:         pd.DataFrame = field(default_factory=pd.DataFrame)
    wearables:        pd.DataFrame = field(default_factory=pd.DataFrame)
    cgm_readings:     pd.DataFrame = field(default_factory=pd.DataFrame)
    ketone_readings:  pd.DataFrame = field(default_factory=pd.DataFrame)
    daily_log:        pd.DataFrame = field(default_factory=pd.DataFrame)
    action_items:     pd.DataFrame = field(default_factory=pd.DataFrame)
    context_notes:    pd.DataFrame = field(default_factory=pd.DataFrame)
    import_log:       pd.DataFrame = field(default_factory=pd.DataFrame)
    nof1_experiments: list[dict]   = field(default_factory=list)


@st.cache_data(ttl=300)
def load_data(user_id: str = DEFAULT_USER) -> HealthData:
    """Load every CSV/JSON for a user. Cached 5 minutes."""
    return HealthData(
        bloodwork=_read_csv("bloodwork.csv", user_id, parse_dates=["date"]),
        protocol=_read_csv("protocol.csv", user_id, parse_dates=["start_date", "end_date"]),
        inbody=_read_csv("inbody.csv", user_id, parse_dates=["date"]),
        training=_read_csv("training.csv", user_id, parse_dates=["date"]),
        wearables=_read_csv("wearables.csv", user_id, parse_dates=["date"]),
        cgm_readings=_read_csv("cgm_readings.csv", user_id, parse_dates=["datetime"]),
        ketone_readings=_read_csv("ketone_readings.csv", user_id, parse_dates=["datetime"]),
        daily_log=_read_csv("daily_log.csv", user_id, parse_dates=["date"]),
        action_items=_read_csv("action_items.csv", user_id, parse_dates=["due_date", "created_date"]),
        context_notes=_read_csv("context_notes.csv", user_id, parse_dates=["date"]),
        import_log=_read_csv("import_log.csv", user_id, parse_dates=["timestamp"]),
        nof1_experiments=_read_json("nof1_experiments.json", user_id),
    )


def refresh_data() -> None:
    """Clear cache and force a rerun. Called by the 🔄 Refresh buttons."""
    st.cache_data.clear()
    st.rerun()


# ────────────────────────────────────────────────────────────────────────────
# Writers — append-only helpers. Phase 1 writes to local CSV; Phase 2 will
# also commit through the GitHub Contents API. Pages call these for any
# form-driven inserts (daily log, ketone reading, context note, etc.).
# ────────────────────────────────────────────────────────────────────────────

# Map filename -> import_log source_type so freshness picks up manual entries.
_MANUAL_SOURCE_TYPES = {
    "daily_log.csv":       "manual_entry",
    "ketone_readings.csv": "manual_entry",
    "cgm_readings.csv":    "manual_entry",
    "context_notes.csv":   "manual_entry",
    "action_items.csv":    "manual_entry",
}


def append_row(filename: str, row: dict, user_id: str = DEFAULT_USER) -> None:
    """Append a single row to a CSV, creating the file if missing.

    Also stamps `import_log.csv` so the freshness badge updates.
    """
    path = _user_dir(user_id) / filename
    df = pd.DataFrame([row])
    if path.exists():
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, mode="w", header=True, index=False)

    # Audit-trail stamp for manually entered feeds.
    source_type = _MANUAL_SOURCE_TYPES.get(filename)
    if source_type:
        log_path = _user_dir(user_id) / "import_log.csv"
        log_row = pd.DataFrame([{
            "timestamp": pd.Timestamp.now().isoformat(timespec="seconds"),
            "source_type": source_type,
            "filename": filename,
            "rows_imported": 1,
            "rows_skipped_duplicate": 0,
            "errors": "",
            "imported_by": "streamlit_form",
        }])
        if log_path.exists():
            log_row.to_csv(log_path, mode="a", header=False, index=False)
        else:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_row.to_csv(log_path, mode="w", header=True, index=False)

    st.cache_data.clear()


def write_json(filename: str, payload: Any, user_id: str = DEFAULT_USER) -> None:
    """Overwrite a JSON file (used for nof1_experiments and similar)."""
    path = _user_dir(user_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(payload, f, indent=2, default=str)
    st.cache_data.clear()


# ────────────────────────────────────────────────────────────────────────────
# Convenience accessors
# ────────────────────────────────────────────────────────────────────────────

def latest_bloodwork_draw(df: pd.DataFrame) -> pd.DataFrame:
    """Return all bloodwork rows from the most recent draw date."""
    if df.empty:
        return df
    latest = df["date"].max()
    return df[df["date"] == latest]


def previous_bloodwork_draw(df: pd.DataFrame) -> pd.DataFrame:
    """Return all bloodwork rows from the second-most-recent draw."""
    if df.empty:
        return df
    dates = sorted(df["date"].unique(), reverse=True)
    if len(dates) < 2:
        return pd.DataFrame()
    return df[df["date"] == dates[1]]
