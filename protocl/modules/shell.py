"""v3.2 — the per-request auth + chrome shell.

``boot()`` is called once at the top of ``app.py`` (before navigation is
built). It:
  1. Guards the request with ``auth.require_auth`` (login / denial / role).
  2. For a brand-new beta user, seeds their profile dir and shows the one-time
     consent screen (and stops until they accept).
  3. Renders the impersonation banner, feedback widget, and logout control.

Everything is import-safe under the test shim because the heavy lifting only
runs when Streamlit actually drives the app.
"""
from __future__ import annotations

import streamlit as st

import auth
import consent
from storage import ProfileStorage


def _render_consent_gate(store: ProfileStorage) -> None:
    """One-time consent screen for beta users (spec 1.4)."""
    st.title("⚗️ Welcome to the Protocōl beta")
    st.write(
        "Before you start, please review and accept the terms below. You can "
        "change the optional setting anytime under **Settings**."
    )
    privacy = st.checkbox(
        "I understand this is a personal beta and my data is stored in a private "
        "Streamlit app. I agree to the privacy notice.",
        key="_consent_privacy",
    )
    owner_vis = st.checkbox(
        "I consent to Ryan viewing my dashboard data to provide feedback and "
        "improve the app. I can revoke this anytime in Settings. (optional)",
        key="_consent_owner_vis",
    )
    if st.button("Continue", type="primary", disabled=not privacy):
        consent.record_consent(privacy_accepted=True, owner_visibility=owner_vis, store=store)
        st.rerun()
    if not privacy:
        st.caption("The first box is required to continue.")
    st.stop()


def boot() -> auth.Principal:
    """Authenticate, gate consent, render chrome. Returns the Principal."""
    principal = auth.require_auth()

    store = ProfileStorage()

    # New beta user: create their dir + templates, then require consent once.
    if principal.role == auth.ROLE_BETA and not store.read_only:
        if not store.exists():
            store.seed_empty()
        if not consent.has_accepted_privacy(store):
            _render_consent_gate(store)

    auth.render_impersonation_banner()
    _render_sidebar(principal)
    return principal


def _render_sidebar(principal: auth.Principal) -> None:
    import feedback

    with st.sidebar:
        st.caption(f"Signed in: {st.session_state.get('display_name', principal.display_name)}")
    feedback.render_sidebar_widget(current_page=_current_page_label())
    auth.logout_button()
    with st.sidebar:
        st.page_link("pages/99_privacy.py", label="Privacy notice", icon="🔒")


def _current_page_label() -> str:
    try:
        ctx = st.session_state.get("_active_page", "")
    except Exception:
        ctx = ""
    return ctx
