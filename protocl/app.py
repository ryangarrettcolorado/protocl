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
from modules.shell import boot
from modules.theme import apply_density, inject_css, render_top_brand


st.set_page_config(
    page_title="Protocōl — Health Intelligence OS",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# v3.2 — authenticate, assign role + profile, gate consent, render chrome.
# This stops the run (login / denial / consent screens) for unauthenticated,
# unauthorized, or not-yet-consented users before any page renders.
boot()


# Make sure the preferences file exists so visibility toggles + appearance
# settings have something to read on the very first run.
ensure_initialized()

prefs = load_preferences()
appearance_cfg = appearance(prefs)

inject_css()
apply_density(appearance_cfg.get("density", "comfortable"))
render_top_brand()

pg = build_navigation()

# v3.5 — wrap page execution in error capture: log + show a friendly page
# instead of a raw traceback. v3.6 — track each page render as a page_view.
# (session_start is opened earlier in shell.boot, before the NPS check, so the
# survey can fire on the literal 7th session.)
try:
    from modules import events
    from storage import ProfileStorage as _PS
    _store = _PS()
    events.track("page_view", page=getattr(pg, "url_path", "") or "", store=_store)
except Exception:
    pass

try:
    pg.run()
except Exception as _exc:  # noqa: BLE001 — last-resort page guard
    from modules import error_capture
    from storage import ProfileStorage as _PS

    _pid = st.session_state.get("profile_id", "") or ""
    _page = getattr(pg, "url_path", "") or ""
    error_capture.capture_error(_exc, page=_page, profile_id=_pid)

    st.error("Something went wrong. We've been notified.")
    st.caption("You can keep using the rest of the app, or send Ryan what happened.")
    if st.button("Send context to Ryan"):
        try:
            from modules import feedback_v2
            feedback_v2.submit_structured(
                sentiment="negative",
                expected="",
                improvement=f"[auto] error on {_page}: {type(_exc).__name__}: {_exc}",
                page=_page,
                store=_PS(),
            )
            st.success("Thanks — context sent.")
        except Exception:
            st.warning("Couldn't send automatically. Use the feedback widget in the sidebar.")
