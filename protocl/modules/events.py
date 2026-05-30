"""v3.6 — privacy-preserving event tracking.

``track(event_name, **properties)`` appends a structured row to the *current
profile's* ``events.csv`` and bumps an **anonymized** daily rollup in
``data/shared/event_rollup_daily.csv`` (``date, event_name, count`` — never a
``profile_id``).

Privacy gates
-------------
- Per-user event detail lives ONLY in ``data/profiles/<id>/events.csv``.
- Tracking is opt-in: a user who turned off analytics consent
  (``user_prefs.analytics_consent``) records *nothing* — not even the
  anonymized rollup.
- The owner may read another user's per-event detail ONLY when that user
  granted v3.2 owner-visibility (``consent.owner_can_view``). The rollup is
  always safe to read because it carries no identity.

Session windows
---------------
``session_start``/``session_end`` are derived from a 30-minute inactivity
window using the user's most recent event timestamp. ``maybe_start_session``
is called by the shell on every page render; it emits ``session_end`` (with the
prior session's duration) followed by ``session_start`` when the gap exceeds
the window.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

import storage
from storage import ProfileStorage, ReadOnlyError
from modules import user_prefs


EVENTS_FILE = "events.csv"
ROLLUP_FILE = "event_rollup_daily.csv"
EVENTS_COLUMNS = ["timestamp", "event_name", "page", "properties_json"]
ROLLUP_COLUMNS = ["date", "event_name", "count"]

SESSION_WINDOW_MIN = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse_ts(raw: Any) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# Core API
# ────────────────────────────────────────────────────────────────────────────

def track(event_name: str, *, page: str = "", store: ProfileStorage | None = None,
          _now_dt: datetime | None = None, **properties: Any) -> None:
    """Log a structured event for the current profile + bump the anon rollup.

    No-op (records nothing) if the user has not consented to analytics. Never
    raises into page code.
    """
    store = store or ProfileStorage()
    try:
        if not user_prefs.analytics_allowed(store):
            return
        now = _now_dt or _now()
        row = {
            "timestamp": _iso(now),
            "event_name": event_name,
            "page": page,
            "properties_json": json.dumps(properties, default=str, sort_keys=True),
        }
        try:
            store.append_csv(EVENTS_FILE, row)
        except ReadOnlyError:
            # Owner impersonating a user must not write into that user's log.
            return
        # Fold the page into the rollup key for page_view so the owner can see
        # *which* pages are popular without any profile_id (still anonymous).
        rollup_key = f"page_view:{page}" if event_name == "page_view" and page else event_name
        _bump_rollup(rollup_key, now)
    except Exception:
        # Telemetry must never take down a page render.
        pass


def _bump_rollup(event_name: str, now: datetime) -> None:
    """Increment the anonymized ``date,event_name,count`` daily rollup.

    Carries NO profile_id — this is the only event data ever written to the
    shared directory.
    """
    date_str = now.date().isoformat()
    path = storage.shared_path(ROLLUP_FILE)
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame(columns=ROLLUP_COLUMNS)
    mask = (df["date"] == date_str) & (df["event_name"] == event_name) if not df.empty else pd.Series([], dtype=bool)
    if not df.empty and mask.any():
        df.loc[mask, "count"] = df.loc[mask, "count"].astype(int) + 1
    else:
        df = pd.concat(
            [df, pd.DataFrame([{"date": date_str, "event_name": event_name, "count": 1}])],
            ignore_index=True,
        )
    df.to_csv(path, index=False)


# ────────────────────────────────────────────────────────────────────────────
# Readers (per-user — owner-gated by caller)
# ────────────────────────────────────────────────────────────────────────────

def read_events(store: ProfileStorage | None = None) -> pd.DataFrame:
    """All events for the current profile (or the owner-pointed store)."""
    store = store or ProfileStorage()
    return store.read_csv(EVENTS_FILE, parse_dates=["timestamp"])


def recent_events(n: int = 5, store: ProfileStorage | None = None) -> list[dict[str, Any]]:
    """Last ``n`` events for the current profile, newest last."""
    df = read_events(store)
    if df.empty:
        return []
    tail = df.tail(n)
    out = []
    for _, r in tail.iterrows():
        out.append({
            "timestamp": str(r.get("timestamp", "")),
            "event_name": r.get("event_name", ""),
            "page": r.get("page", ""),
            "properties_json": r.get("properties_json", "{}"),
        })
    return out


def read_rollup() -> pd.DataFrame:
    """The anonymized app-wide daily rollup (safe — contains no profile_id)."""
    return storage.read_shared_csv(ROLLUP_FILE, parse_dates=["date"])


def distinct_session_starts(store: ProfileStorage | None = None) -> int:
    """How many ``session_start`` events this profile has recorded."""
    df = read_events(store)
    if df.empty or "event_name" not in df.columns:
        return 0
    return int((df["event_name"] == "session_start").sum())


def last_event_time(store: ProfileStorage | None = None) -> datetime | None:
    df = read_events(store)
    if df.empty or "timestamp" not in df.columns:
        return None
    ts = pd.to_datetime(df["timestamp"], errors="coerce").dropna()
    if ts.empty:
        return None
    out = ts.max().to_pydatetime()
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


# ────────────────────────────────────────────────────────────────────────────
# Session windowing
# ────────────────────────────────────────────────────────────────────────────

def is_new_session(last_ts: datetime | None, now: datetime,
                   window_min: int = SESSION_WINDOW_MIN) -> bool:
    """True if ``now`` opens a new session relative to ``last_ts``."""
    if last_ts is None:
        return True
    return (now - last_ts) > timedelta(minutes=window_min)


def maybe_start_session(store: ProfileStorage | None = None,
                        _now_dt: datetime | None = None) -> bool:
    """Emit session_end (if a prior session lapsed) + session_start when the
    inactivity window is exceeded. Returns True when a new session started.
    """
    store = store or ProfileStorage()
    try:
        if not user_prefs.analytics_allowed(store):
            return False
        now = _now_dt or _now()
        last = last_event_time(store)
        if not is_new_session(last, now):
            return False
        if last is not None:
            duration_min = round((last - _session_open_time(store, last)).total_seconds() / 60, 1)
            track("session_end", store=store, _now_dt=now,
                  prev_session_last=_iso(last), duration_min=duration_min)
        track("session_start", store=store, _now_dt=now)
        return True
    except Exception:
        return False


def _session_open_time(store: ProfileStorage, before: datetime) -> datetime:
    """Best-effort: timestamp of the last ``session_start`` at/just before
    ``before`` (used to compute a closed session's duration)."""
    df = read_events(store)
    if df.empty:
        return before
    starts = df[df["event_name"] == "session_start"]
    if starts.empty:
        return before
    ts = pd.to_datetime(starts["timestamp"], errors="coerce").dropna()
    ts = ts[ts <= pd.Timestamp(before)]
    if ts.empty:
        return before
    out = ts.max().to_pydatetime()
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
