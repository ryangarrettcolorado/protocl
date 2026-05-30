"""Home — data-rich seven-row command center.

This page is the new landing destination (formerly the Overview page).
Composition logic lives in ``modules.home_dashboard``; this file is just
the wrapper that ``st.navigation`` registers and runs.
"""
from __future__ import annotations

import streamlit as st

from modules import changelog
from modules.data_loader import refresh_data
from modules.freshness import render_freshness_strip
from modules.home_dashboard import render_home
from modules.preferences import load_preferences, profile
from modules.setup_hero import render_setup_hero
from modules.theme import inject_css
from storage import ProfileStorage


inject_css()

prefs = load_preferences()
user_profile = profile(prefs)

# Header row
col_title, col_refresh = st.columns([6, 1])
with col_title:
    name = user_profile.get("display_name", "Ryan")
    st.title(f"Welcome back, {name}")
    st.caption("How am I doing right now · what changed · what needs attention")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

# v3.5 — "What's new" banner, shown once per unseen version (dismissible).
_cl_store = ProfileStorage()
if changelog.should_show_home_banner(_cl_store):
    _latest = changelog.latest_version()
    bc1, bc2, bc3 = st.columns([6, 2, 1])
    with bc1:
        st.info(f"🎉 Protocōl {_latest} is here — see what's new.")
    with bc2:
        st.page_link("pages/96_whats_new.py", label="See what's new", icon="📣")
    with bc3:
        if st.button("Dismiss", key="_cl_banner_dismiss"):
            changelog.dismiss_banner(_latest, _cl_store)
            st.rerun()

# v3.6 — drop-off re-engagement nudge (set by the daily detector at 7d idle).
from modules import user_prefs as _up

_nudge = _up.get("dropoff_nudge", None, _cl_store)
if _nudge:
    nc1, nc2 = st.columns([8, 1])
    with nc1:
        st.warning(f"👋 {_nudge}")
    with nc2:
        if st.button("Dismiss", key="_dropoff_nudge_dismiss"):
            _up.set_value("dropoff_nudge", None, _cl_store)
            st.rerun()

# v3.4 — adaptive setup hero. Renders only while coverage < 50% and not snoozed;
# the owner's rich data keeps coverage ≥ 50%, so this is a no-op for him.
render_setup_hero()

render_freshness_strip()

render_home(prefs)
