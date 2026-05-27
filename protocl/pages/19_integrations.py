"""Integrations — manage every data source that feeds Protocōl.

Three sections:
    1. Connected — live API/connector integrations (Strava, Apple Health, GitHub)
    2. File-uploaded — sources that flow in via Imports (Bloodwork, InBody, GPX, ECG, Protocol)
    3. Coming soon — placeholders for upcoming integrations (CGM, Fullscript, etc.)

Each card shows: brand mark, name, category, status pill, last-sync timestamp
(pulled from import_log.csv), and a contextual action button.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.freshness import LOG_PATH, _read_log
from modules.integrations import CATALOG, Integration, by_status
from modules.theme import inject_css


inject_css()


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _latest_per_source_type() -> dict[str, pd.Timestamp]:
    """Return latest import timestamp keyed by raw source_type."""
    df = _read_log()
    if df.empty:
        return {}
    grouped = df.groupby("source_type")["timestamp"].max()
    return {k: v for k, v in grouped.items()}


def _humanize(ts: pd.Timestamp | None) -> str:
    if ts is None or pd.isna(ts):
        return "Never"
    now = datetime.now()
    delta = now - ts.to_pydatetime().replace(tzinfo=None)
    secs = delta.total_seconds()
    if secs < 60:
        return "Just now"
    if secs < 3600:
        return f"{int(secs/60)}m ago"
    if secs < 86400:
        return f"{int(secs/3600)}h ago"
    days = int(secs / 86400)
    if days == 1:
        return "Yesterday"
    if days < 30:
        return f"{days} days ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    return ts.strftime("%b %Y")


def _latest_for(integ: Integration, lookup: dict[str, pd.Timestamp]) -> pd.Timestamp | None:
    candidates = [lookup[s] for s in integ.source_types if s in lookup]
    return max(candidates) if candidates else None


# ────────────────────────────────────────────────────────────────────────────
# Status pill CSS
# ────────────────────────────────────────────────────────────────────────────

STATUS_STYLES = {
    "connected": (
        "background:rgba(63,191,127,0.15); color:#3FBF7F; "
        "border:1px solid rgba(63,191,127,0.40);"
    ),
    "file_based": (
        "background:rgba(255,182,18,0.12); color:#FFB612; "
        "border:1px solid rgba(255,182,18,0.35);"
    ),
    "coming_soon": (
        "background:rgba(255,255,255,0.04); color:#888; "
        "border:1px solid rgba(255,255,255,0.10);"
    ),
}

STATUS_LABEL = {
    "connected": "● Connected",
    "file_based": "File-based",
    "coming_soon": "Coming soon",
}


def _render_card(integ: Integration, lookup: dict[str, pd.Timestamp]) -> None:
    """Render a single integration card with action button below."""
    ts = _latest_for(integ, lookup)
    last_sync = _humanize(ts)
    pill_css = STATUS_STYLES[integ.status]
    pill_text = STATUS_LABEL[integ.status]

    is_soon = integ.status == "coming_soon"
    opacity = "0.55" if is_soon else "1"

    card_html = f"""
    <div style="
        background:rgba(255,255,255,0.04);
        border:1px solid rgba(255,255,255,0.08);
        border-radius:12px;
        padding:1.1rem 1.1rem 0.9rem 1.1rem;
        height:100%;
        display:flex; flex-direction:column;
        opacity:{opacity};
    ">
      <div style="display:flex; align-items:flex-start; gap:0.85rem; margin-bottom:0.7rem;">
        <div style="flex-shrink:0; width:44px; height:44px;
                    display:flex; align-items:center; justify-content:center;">
          {integ.svg}
        </div>
        <div style="flex:1; min-width:0;">
          <div style="font-weight:600; color:#E8E8EA; font-size:0.98rem;
                      line-height:1.2; margin-bottom:0.2rem;">
            {integ.name}
          </div>
          <div style="font-size:0.7rem; color:#888; letter-spacing:0.04em;
                      text-transform:uppercase;">
            {integ.category}
          </div>
        </div>
        <span style="display:inline-flex; align-items:center;
                     padding:0.18rem 0.55rem; border-radius:999px;
                     font-size:0.66rem; font-weight:600; letter-spacing:0.02em;
                     {pill_css} flex-shrink:0;">
          {pill_text}
        </span>
      </div>
      <div style="color:#A8A8AC; font-size:0.82rem; line-height:1.45;
                  margin-bottom:0.75rem; flex:1;">
        {integ.description}
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center;
                  padding-top:0.55rem; border-top:1px solid rgba(255,255,255,0.06);
                  font-size:0.74rem;">
        <span style="color:#888;">Last sync</span>
        <span style="color:#E8E8EA; font-variant-numeric:tabular-nums;">{last_sync}</span>
      </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    # Action button (rendered separately so it remains interactive)
    if integ.action_label:
        button_key = f"action_{integ.key}"
        disabled = is_soon and integ.action_label == "Notify me"  # keep clickable, no-op
        # Use a small button below the card
        if st.button(integ.action_label, key=button_key, use_container_width=True):
            _handle_action(integ)
        if integ.action_hint:
            st.caption(integ.action_hint)


def _handle_action(integ: Integration) -> None:
    """Wire up button clicks. Most just show a toast — the heavy lifting
    lives on the Imports page or in the connector framework."""
    if integ.status == "coming_soon":
        st.toast(f"You'll be notified when {integ.name} ships.", icon="🔔")
        return
    if integ.connection_type == "file_upload":
        st.toast(f"Head to the Imports page to upload {integ.name}.", icon="📥")
        return
    if integ.connection_type in {"oauth_api", "connector"}:
        if integ.action_label.lower() == "disconnect":
            st.toast(
                f"Disconnect from the connector settings — this only stops sync. "
                f"Existing data stays in place.",
                icon="ℹ️",
            )
        else:
            st.toast(f"Open the {integ.name} connector to manage it.", icon="🔗")


def _render_grid(items: list[Integration], lookup: dict[str, pd.Timestamp],
                 cols: int = 3) -> None:
    """Render a responsive grid of integration cards."""
    if not items:
        st.info("Nothing here yet.")
        return
    for row_start in range(0, len(items), cols):
        row = items[row_start:row_start + cols]
        columns = st.columns(cols)
        for col, integ in zip(columns, row):
            with col:
                _render_card(integ, lookup)
        # Pad empty cells so the row aligns
        for col in columns[len(row):]:
            with col:
                st.markdown("<div></div>", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Page
# ────────────────────────────────────────────────────────────────────────────

col_title, col_reload = st.columns([6, 1])
with col_title:
    st.title("Integrations")
    st.caption(
        "Every data source feeding Protocōl. Connect APIs, upload files, "
        "and queue up what's coming next."
    )
with col_reload:
    if st.button("↻ Reload", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


lookup = _latest_per_source_type()

# Summary strip ──────────────────────────────────────────────────────────────
n_connected = len(by_status("connected"))
n_file = len(by_status("file_based"))
n_soon = len(by_status("coming_soon"))

summary_html = f"""
<div style="display:flex; gap:0.6rem; flex-wrap:wrap;
            margin:0.2rem 0 1.3rem 0;">
  <span style="padding:0.35rem 0.85rem; border-radius:999px;
               background:rgba(63,191,127,0.12); color:#3FBF7F;
               border:1px solid rgba(63,191,127,0.30);
               font-size:0.78rem; font-weight:500;">
    {n_connected} connected
  </span>
  <span style="padding:0.35rem 0.85rem; border-radius:999px;
               background:rgba(255,182,18,0.10); color:#FFB612;
               border:1px solid rgba(255,182,18,0.30);
               font-size:0.78rem; font-weight:500;">
    {n_file} file-based
  </span>
  <span style="padding:0.35rem 0.85rem; border-radius:999px;
               background:rgba(255,255,255,0.04); color:#888;
               border:1px solid rgba(255,255,255,0.10);
               font-size:0.78rem; font-weight:500;">
    {n_soon} coming soon
  </span>
</div>
"""
st.markdown(summary_html, unsafe_allow_html=True)


# § 1 — Connected ────────────────────────────────────────────────────────────
st.markdown("### Connected")
st.caption("Live API + connector integrations. These auto-sync on a schedule.")
_render_grid(by_status("connected"), lookup)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

# § 2 — File-based ───────────────────────────────────────────────────────────
st.markdown("### File-based sources")
st.caption(
    "Uploaded via the Imports page and parsed into structured rows. "
    "All flow through `data/ryan/` CSV/JSON loaders."
)
_render_grid(by_status("file_based"), lookup)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

# § 3 — Coming soon ──────────────────────────────────────────────────────────
st.markdown("### Coming soon")
st.caption("Queued integrations. Tap Notify me to be pinged when they land.")
_render_grid(by_status("coming_soon"), lookup)

st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)

# Footnote ───────────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <div style="margin-top:1.5rem; padding:0.9rem 1.1rem; border-radius:10px;
                background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
                color:#888; font-size:0.78rem; line-height:1.5;">
      <strong style="color:#FFB612;">How sync works.</strong>
      Strava + Apple Health refresh daily at 7:00 AM MDT via the daily cron
      (<code>scripts/daily_sync.py</code>). File-based sources update whenever
      you upload through Imports. Last-sync timestamps read from
      <code>data/ryan/import_log.csv</code>.
    </div>
    """,
    unsafe_allow_html=True,
)
