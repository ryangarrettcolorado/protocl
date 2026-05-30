"""v3.6 — owner analytics aggregations.

Pure-ish computation helpers behind the owner analytics dashboard. Engagement
metrics come from the **anonymized** daily rollup
(``data/shared/event_rollup_daily.csv`` — no profile_id), so they never expose
identity. Funnel + drop-off views read allowlist + shared logs.

No LLM, no external calls.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from modules import events


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Engagement (from anonymized rollup) ──────────────────────────────────────

def daily_active(rollup: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily ``session_start`` counts as a DAU proxy. Columns: date, count."""
    df = rollup if rollup is not None else events.read_rollup()
    if df.empty or "event_name" not in df.columns:
        return pd.DataFrame(columns=["date", "count"])
    sub = df[df["event_name"] == "session_start"].copy()
    if sub.empty:
        return pd.DataFrame(columns=["date", "count"])
    out = sub.groupby("date", as_index=False)["count"].sum()
    return out.sort_values("date")


def weekly_active(rollup: pd.DataFrame | None = None) -> pd.DataFrame:
    """WAU proxy: session_start counts bucketed by ISO week. Columns: week, count."""
    daily = daily_active(rollup)
    if daily.empty:
        return pd.DataFrame(columns=["week", "count"])
    daily = daily.copy()
    daily["week"] = (
        pd.to_datetime(daily["date"], errors="coerce", utc=True)
        .dt.to_period("W").apply(lambda p: p.start_time.date())
    )
    out = daily.groupby("week", as_index=False)["count"].sum()
    return out.sort_values("week")


def top_pages(rollup: pd.DataFrame | None = None, top_n: int = 10) -> pd.DataFrame:
    """Most-viewed pages from page_view events. Columns: page, count.

    The rollup keys by event_name only, so page detail comes from the
    ``page_view:<page>`` convention if present, else the bare ``page_view``
    total. Falls back gracefully when no page granularity exists.
    """
    df = rollup if rollup is not None else events.read_rollup()
    if df.empty or "event_name" not in df.columns:
        return pd.DataFrame(columns=["page", "count"])
    pv = df[df["event_name"].astype(str).str.startswith("page_view")].copy()
    if pv.empty:
        return pd.DataFrame(columns=["page", "count"])
    pv["page"] = pv["event_name"].astype(str).str.replace("page_view:", "", regex=False)
    pv["page"] = pv["page"].replace("page_view", "(unknown)")
    out = pv.groupby("page", as_index=False)["count"].sum()
    return out.sort_values("count", ascending=False).head(top_n)


# ── Funnel health (signup → consent → first-data → 3rd visit) ────────────────

def funnel_counts(allowlist: dict | None = None) -> dict[str, int]:
    """Count profiles at each onboarding stage. Per-user reads via ProfileStorage.

    Stages:
      signed_up   — on the allowlist (has a profile dir)
      consented   — accepted the privacy notice
      first_data  — has at least one event recorded
      returned    — reached a 3rd distinct session
    """
    import consent
    from auth import _slugify_email, load_allowlist
    from storage import ProfileStorage

    allow = allowlist if allowlist is not None else load_allowlist()
    pids: list[str] = []
    owner = (allow.get("owner") or {}).get("email")
    if owner:
        pids.append("ryan")
    for entry in allow.get("beta_users") or []:
        email = (entry.get("email") or "").strip().lower()
        if email and not email.endswith("@example.com"):
            pids.append(_slugify_email(email))

    signed_up = consented = first_data = returned = 0
    for pid in pids:
        store = ProfileStorage()
        store.profile_id = pid
        store.read_only = True
        if not store.exists():
            continue
        signed_up += 1
        if consent.has_accepted_privacy(store):
            consented += 1
        sessions = events.distinct_session_starts(store)
        if not events.read_events(store).empty:
            first_data += 1
        if sessions >= 3:
            returned += 1
    return {
        "signed_up": signed_up,
        "consented": consented,
        "first_data": first_data,
        "returned": returned,
    }


# ── Drop-off watchlist ───────────────────────────────────────────────────────

def dropoff_watchlist(allowlist: dict | None = None,
                      now: datetime | None = None,
                      min_days: int = 7) -> pd.DataFrame:
    """Profiles inactive for >= ``min_days``. Columns: profile_id, days_inactive."""
    from modules import dropoff, sync_orchestrator

    now = now or _now()
    rows: list[dict] = []
    for pid in sync_orchestrator._enabled_profiles(allowlist):
        if pid == "ryan":
            continue
        d = dropoff.days_inactive(pid, now)
        if d is not None and d >= min_days:
            rows.append({"profile_id": pid, "days_inactive": round(d, 1)})
    df = pd.DataFrame(rows, columns=["profile_id", "days_inactive"])
    return df.sort_values("days_inactive", ascending=False) if not df.empty else df
