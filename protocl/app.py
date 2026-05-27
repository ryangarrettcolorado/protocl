"""Protocōl — Health Intelligence OS · v1.5 nav shell.

This file is now a thin entry point:
1. Sets the global ``st.set_page_config`` once for the whole app.
2. Injects the shared CSS.
3. Renders the brand bar above the top nav.
4. Ensures the user preferences file exists.
5. Hands control to the grouped top navigation built by ``modules.nav``.

The Home dashboard itself lives in ``pages/01_home.py`` so it routes through
the same nav system as every other page.
"""
from __future__ import annotations

import streamlit as st

from modules.nav import build_navigation
from modules.preferences import appearance, ensure_initialized, load_preferences
from modules.theme import apply_density, inject_css, render_top_brand


st.set_page_config(
    page_title="Protocōl — Health Intelligence OS",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# Make sure the preferences file exists so visibility toggles + appearance
# settings have something to read on the very first run.
ensure_initialized()

prefs = load_preferences()
appearance_cfg = appearance(prefs)

inject_css()
apply_density(appearance_cfg.get("density", "comfortable"))
render_top_brand()

pg = build_navigation()
pg.run()
