"""v3.4 Adaptive UI — Layer 2: the "Unlock this section" locked card.

When a data source is missing, a page renders a single, polite card inviting
the user to add data — instead of an empty chart or table. The card's primary
CTA opens the per-source add-data modal; a secondary link routes to the central
Imports page. A dismiss [×] snoozes the nudge for 30 days, recorded per source
in ``dismissed_nudges.json`` under the profile directory.

Dismissal state is per-profile (via :class:`storage.ProfileStorage`), so one
user snoozing a nudge never affects another.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import streamlit as st

from storage import ProfileStorage, ReadOnlyError
from modules.data_presence import get_source

DISMISS_FILE = "dismissed_nudges.json"
DISMISS_WINDOW_DAYS = 30


def _store_or_default(store: ProfileStorage | None) -> ProfileStorage:
    return store if store is not None else ProfileStorage()


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def is_dismissed(source_key: str, store: ProfileStorage | None = None,
                 *, now: datetime | None = None) -> bool:
    """True if the nudge for ``source_key`` was dismissed within 30 days."""
    store = _store_or_default(store)
    data = store.read_json(DISMISS_FILE, default={}) or {}
    entry = data.get(source_key) if isinstance(data, dict) else None
    if not entry:
        return False
    dismissed_at = _parse_ts(entry.get("dismissed_at"))
    if dismissed_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now - dismissed_at < timedelta(days=DISMISS_WINDOW_DAYS)


def dismiss_nudge(source_key: str, store: ProfileStorage | None = None) -> None:
    """Record a dismissal timestamp for ``source_key`` (no-op if read-only)."""
    store = _store_or_default(store)
    data = store.read_json(DISMISS_FILE, default={}) or {}
    if not isinstance(data, dict):
        data = {}
    data[source_key] = {"dismissed_at": datetime.now(timezone.utc).isoformat()}
    try:
        store.write_json(DISMISS_FILE, data)
    except ReadOnlyError:
        # Owner impersonating a beta user can't write — silently skip; the
        # nudge simply re-appears next session, which is acceptable.
        pass


def render_locked_card(source_key: str, *, dismissible: bool = True,
                       store: ProfileStorage | None = None) -> None:
    """Render the "Unlock this section" card for a missing data source.

    Returns ``None`` and renders nothing if the nudge is currently dismissed —
    the caller decides what (if any) fallback to show.
    """
    store = _store_or_default(store)
    if dismissible and is_dismissed(source_key, store):
        return None

    src = get_source(source_key)

    header_cols = st.columns([8, 1])
    with header_cols[0]:
        st.markdown(
            f"<div style='font-size:1.05rem;font-weight:600;color:#F0F0F0;'>"
            f"{src.icon} {src.label}</div>",
            unsafe_allow_html=True,
        )
    with header_cols[1]:
        if dismissible and st.button("×", key=f"dismiss_{source_key}",
                                     help="Hide this for 30 days"):
            dismiss_nudge(source_key, store)
            st.rerun()

    if src.value_prop:
        st.markdown(
            f"<div style='color:#A0A0A0;font-size:0.9rem;margin:0.3rem 0 0.7rem 0;'>"
            f"{src.value_prop}</div>",
            unsafe_allow_html=True,
        )

    # Primary CTA opens the per-source modal; import lazily to avoid a cycle.
    from modules.add_data_modal import open_add_data_modal

    cta_cols = st.columns([3, 2])
    with cta_cols[0]:
        if st.button(f"{src.add_data_cta} →", key=f"unlock_{source_key}",
                     type="primary", use_container_width=True):
            open_add_data_modal(source_key)
    with cta_cols[1]:
        try:
            from modules.nav import page_link
            page_link(src.add_data_route, label="More options ›")
        except Exception:
            st.caption("More options ›")
