"""v3.4 Adaptive UI — Layer 1: the data presence registry.

A single catalog of every data source the app consumes, plus the helpers
pages use to decide what to render. The contract is small and pure where it
can be: a source either *has data* (enough rows to show anything), has enough
for a *trend* (a multi-point chart), or is *hidden* (nothing yet).

All reads go through :class:`storage.ProfileStorage`, so presence is always
scoped to the current session's profile — never another user's directory.
The owner, whose directory is rich, lands on ``active`` for nearly everything
and therefore sees the unchanged, data-dense experience.

There are NO LLM calls here; this is pure UX state logic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import pandas as pd

from storage import ProfileStorage


# ────────────────────────────────────────────────────────────────────────────
# DataSource descriptor
# ────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DataSource:
    key: str                          # canonical id: "bloodwork", "wearables", ...
    label: str                        # human label: "Bloodwork"
    files: list[str]                  # CSVs under the profile dir
    min_rows: int = 1                 # rows in any file to count as "has data"
    min_rows_for_trend: int = 3       # rows needed for trend visualizations
    freshness_days: int | None = None  # None = no recency requirement
    date_col: str | None = None       # column used for freshness, if any
    add_data_route: str = "imports"   # central Imports page key
    add_data_cta: str = "Add data"    # primary button label
    value_prop: str = ""              # one-sentence pitch for the locked card
    icon: str = "📊"
    weight: int = 1                   # importance weight for coverage math
    # Optional column filter: only rows where ``filter_col`` is non-null count.
    # Used by sources that share a file with another source (e.g. sleep lives
    # in wearables.csv; strava lives in training.csv).
    filter_cols: list[str] = field(default_factory=list)


# ────────────────────────────────────────────────────────────────────────────
# Registry catalog — one entry per data type the app consumes.
#
# Importance weights drive data_coverage_pct():
#   bloodwork=3, wearables=2, training=2, inbody=2, cgm=1, everything else=1.
# Sources that are *views* over another source's file (strava, function_health,
# sleep) are excluded from coverage so we don't double-count a single import.
# ────────────────────────────────────────────────────────────────────────────

_CATALOG: dict[str, DataSource] = {}


def _register(src: DataSource) -> None:
    _CATALOG[src.key] = src


_register(DataSource(
    key="bloodwork", label="Bloodwork", files=["bloodwork.csv"],
    min_rows_for_trend=3, freshness_days=120, date_col="date",
    add_data_route="imports", add_data_cta="Upload your first lab PDF",
    value_prop="Track 50+ biomarkers and your ApoB / Lp(a) / hormone trends.",
    icon="🩸", weight=3,
))
_register(DataSource(
    key="inbody", label="Body Composition", files=["inbody.csv"],
    min_rows_for_trend=2, freshness_days=30, date_col="date",
    add_data_route="body_composition", add_data_cta="Log a body-comp scan",
    value_prop="Watch body fat, muscle mass, and visceral fat over time.",
    icon="📐", weight=2,
))
_register(DataSource(
    key="wearables", label="Wearables (HR/HRV/Sleep)", files=["wearables.csv"],
    min_rows_for_trend=3, freshness_days=3, date_col="date",
    add_data_route="integrations", add_data_cta="Connect a wearable",
    value_prop="See HRV, RHR, sleep stages, and recovery score trends.",
    icon="⌚", weight=2,
))
_register(DataSource(
    key="training", label="Training Activity", files=["training.csv"],
    min_rows_for_trend=3, freshness_days=14, date_col="date",
    add_data_route="integrations", add_data_cta="Connect Strava",
    value_prop="Visualize cardio volume, Z2 dose, and cycling load.",
    icon="🏃", weight=2,
))
_register(DataSource(
    key="cgm", label="Continuous Glucose", files=["cgm_readings.csv"],
    min_rows_for_trend=3, freshness_days=2, date_col="datetime",
    add_data_route="imports", add_data_cta="Upload a CGM export",
    value_prop="Spot glucose spikes, time-in-range, and meal responses.",
    icon="🍬", weight=1,
))
_register(DataSource(
    key="ketones", label="Ketones", files=["ketone_readings.csv"],
    min_rows_for_trend=3, freshness_days=14, date_col="datetime",
    add_data_route="imports", add_data_cta="Add a ketone reading",
    value_prop="Track ketone state for fasting and metabolic experiments.",
    icon="🔬", weight=1,
))
_register(DataSource(
    key="protocol", label="Protocol (Meds/Peptides/Supps)", files=["protocol.csv"],
    min_rows_for_trend=1, freshness_days=None, date_col="start_date",
    add_data_route="protocol", add_data_cta="Add a compound",
    value_prop="Track compounds, dosing, and adherence.",
    icon="⚗️", weight=1,
))
_register(DataSource(
    key="daily_log", label="Daily Log", files=["daily_log.csv"],
    min_rows_for_trend=3, freshness_days=3, date_col="date",
    add_data_route="daily_trackers", add_data_cta="Log today",
    value_prop="Capture morning mood, energy, soreness, and notes.",
    icon="📓", weight=1,
))
# ── view sources (share a file with a primary source; excluded from coverage) ─
_register(DataSource(
    key="strava", label="Strava", files=["training.csv"],
    min_rows_for_trend=3, freshness_days=7, date_col="date",
    add_data_route="integrations", add_data_cta="Connect Strava",
    value_prop="Pull rides and runs with HR, power, and TSS.",
    icon="🚴", weight=0, filter_cols=["distance_miles", "distance_km", "distance_mi", "tss"],
))
_register(DataSource(
    key="function_health", label="Function Health", files=["bloodwork.csv"],
    min_rows_for_trend=1, freshness_days=None, date_col="date",
    add_data_route="function_health_import", add_data_cta="Import Function PDF",
    value_prop="Import 100+ Function Health biomarkers from PDF.",
    icon="🧬", weight=0, filter_cols=["source_lab"],
))
_register(DataSource(
    key="sleep", label="Sleep", files=["wearables.csv"],
    min_rows_for_trend=3, freshness_days=3, date_col="date",
    add_data_route="integrations", add_data_cta="Connect a sleep tracker",
    value_prop="Sleep score, stages, consistency, and HRV correlation.",
    icon="😴", weight=0, filter_cols=["sleep_score", "sleep_duration_hrs"],
))


# ────────────────────────────────────────────────────────────────────────────
# Catalog accessors
# ────────────────────────────────────────────────────────────────────────────

def get_source(source_key: str) -> DataSource:
    """Lookup a source. Raises ``KeyError`` if unknown."""
    return _CATALOG[source_key]


def all_sources() -> list[DataSource]:
    """The full catalog, in registration order."""
    return list(_CATALOG.values())


# ────────────────────────────────────────────────────────────────────────────
# Row counting
# ────────────────────────────────────────────────────────────────────────────

def _store_or_default(store: ProfileStorage | None) -> ProfileStorage:
    return store if store is not None else ProfileStorage()


def _filtered_rows(df: pd.DataFrame, src: DataSource) -> int:
    """Number of usable rows for ``src`` in ``df``.

    For a view source (``filter_cols`` set), a row only counts when at least
    one of the filter columns is present and non-null — that's how we tell a
    Strava-sourced training row from a manually logged one, or a sleep night
    from a bare wearables row.
    """
    if df.empty:
        return 0
    if not src.filter_cols:
        return len(df)
    present = [c for c in src.filter_cols if c in df.columns]
    if not present:
        return 0
    mask = df[present].notna().any(axis=1)
    return int(mask.sum())


def _row_count(src: DataSource, store: ProfileStorage) -> int:
    """Max usable row count across the source's files."""
    best = 0
    for fname in src.files:
        df = store.read_csv(fname)
        best = max(best, _filtered_rows(df, src))
    return best


# ────────────────────────────────────────────────────────────────────────────
# Presence helpers
# ────────────────────────────────────────────────────────────────────────────

def has_data(source_key: str, *, for_trend: bool = False,
             store: ProfileStorage | None = None) -> bool:
    """True if the profile has enough rows of ``source_key`` data.

    ``for_trend=True`` raises the bar to ``min_rows_for_trend`` — the number a
    multi-point chart needs to be meaningful.
    """
    src = get_source(source_key)
    store = _store_or_default(store)
    count = _row_count(src, store)
    threshold = src.min_rows_for_trend if for_trend else src.min_rows
    return count >= threshold


# Coverage uses only the weighted primary sources (weight > 0). View sources
# (strava/function_health/sleep) are deliberately weight 0 so importing one
# bloodwork PDF doesn't get counted three times.
def _coverage_sources() -> list[DataSource]:
    return [s for s in _CATALOG.values() if s.weight > 0]


def data_coverage_pct(store: ProfileStorage | None = None) -> int:
    """Return 0-100: the share of weighted source-importance the profile has.

    Counts sources where :func:`has_data` is True, weighted by importance
    (bloodwork=3, wearables/training/inbody=2, everything else=1).
    """
    store = _store_or_default(store)
    sources = _coverage_sources()
    total_weight = sum(s.weight for s in sources)
    if total_weight == 0:
        return 0
    have = sum(s.weight for s in sources if has_data(s.key, store=store))
    return int(round(have / total_weight * 100))


def freshness_state(source_key: str,
                    store: ProfileStorage | None = None) -> Literal["fresh", "stale", "missing"]:
    """Combine presence + recency.

    - ``missing`` — no data at all.
    - ``stale``   — data exists but the most recent row is older than
      ``freshness_days`` (sources with no recency requirement never go stale).
    - ``fresh``   — data exists and is within the freshness window.
    """
    src = get_source(source_key)
    store = _store_or_default(store)
    if not has_data(source_key, store=store):
        return "missing"
    if src.freshness_days is None or not src.date_col:
        return "fresh"

    latest = _latest_date(src, store)
    if latest is None:
        return "fresh"  # present but undated — treat as fresh, not stale
    age_days = (datetime.now(timezone.utc) - latest).days
    return "stale" if age_days > src.freshness_days else "fresh"


def _latest_date(src: DataSource, store: ProfileStorage) -> datetime | None:
    """The most recent timestamp across the source's files, as tz-aware UTC."""
    newest: pd.Timestamp | None = None
    for fname in src.files:
        df = store.read_csv(fname)
        if df.empty or src.date_col not in df.columns:
            continue
        if src.filter_cols:
            present = [c for c in src.filter_cols if c in df.columns]
            if present:
                df = df[df[present].notna().any(axis=1)]
        ts = pd.to_datetime(df[src.date_col], errors="coerce").dropna()
        if ts.empty:
            continue
        candidate = ts.max()
        if newest is None or candidate > newest:
            newest = candidate
    if newest is None:
        return None
    py = newest.to_pydatetime()
    return py if py.tzinfo else py.replace(tzinfo=timezone.utc)


def visibility_state(source_key: str,
                     store: ProfileStorage | None = None,
                     *, show_empty: bool | None = None) -> Literal["active", "stub", "hidden"]:
    """The decision the UI uses to render a section.

    - ``active`` — enough rows for a trend (``has_data(for_trend=True)``).
    - ``stub``   — has data but not enough for a trend.
    - ``hidden`` — no data.

    When ``show_empty`` is True (the Settings "Show all sections" toggle), every
    source resolves to ``active`` so empty-state messaging renders instead of
    the section disappearing. ``show_empty=None`` reads the current profile's
    preference.
    """
    if show_empty is None:
        show_empty = show_empty_sections()
    if show_empty:
        return "active"

    store = _store_or_default(store)
    if has_data(source_key, for_trend=True, store=store):
        return "active"
    if has_data(source_key, store=store):
        return "stub"
    return "hidden"


# ────────────────────────────────────────────────────────────────────────────
# "Show all sections" preference
# ────────────────────────────────────────────────────────────────────────────

def show_empty_sections() -> bool:
    """Read the current profile's ``show_empty_sections`` preference.

    Default is OFF for beta users and ON for the owner — the owner authors
    against the full layout, beta friends get the curated empty-hiding view.
    Reads ``user_preferences.json`` for the active profile; falls back to the
    role-based default when the key is absent.
    """
    import streamlit as st
    from modules import preferences as _prefs

    try:
        profile_id = st.session_state.get("profile_id")
    except Exception:
        profile_id = None
    profile_id = profile_id or "ryan"

    # Preferences are stored single-tenant in this codebase (v3.2 isolation
    # applies to the CSV data layer, not user_preferences.json); read them the
    # same way every other page does so the toggle round-trips through Settings.
    try:
        prefs = _prefs.load_preferences()
    except Exception:
        prefs = {}

    appearance = prefs.get("appearance") or {}
    if "show_empty_sections" in appearance:
        return bool(appearance["show_empty_sections"])

    # Default when unset: owner ON, every other (beta) user OFF.
    try:
        role = st.session_state.get("role")
    except Exception:
        role = None
    return role == "owner" or profile_id == "ryan"


# ────────────────────────────────────────────────────────────────────────────
# Quick-win ranking (used by the setup hero)
# ────────────────────────────────────────────────────────────────────────────

def hidden_sources_ranked(store: ProfileStorage | None = None) -> list[DataSource]:
    """Weighted primary sources the profile is still missing, highest first."""
    store = _store_or_default(store)
    missing = [s for s in _coverage_sources() if not has_data(s.key, store=store)]
    return sorted(missing, key=lambda s: s.weight, reverse=True)
