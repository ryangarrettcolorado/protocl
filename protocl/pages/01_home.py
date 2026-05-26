"""Home — data-rich seven-row command center.

This page is the new landing destination (formerly the Overview page).
Composition logic lives in ``modules.home_dashboard``; this file is just
the wrapper that ``st.navigation`` registers and runs.
"""
from __future__ import annotations

import streamlit as st

from modules.data_loader import refresh_data
from modules.home_dashboard import render_home
from modules.preferences import load_preferences, profile
from modules.theme import inject_css


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

render_home(prefs)
