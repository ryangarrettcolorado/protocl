"""v3.2 — beta feedback widget backend.

Feedback is written twice: to the user's own ``feedback.csv`` (so they can see
their own history) and appended to the app-wide ``data/shared/all_feedback.csv``
(so the owner can triage everyone's feedback in one place).
"""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

import storage
from storage import ProfileStorage


GLOBAL_FILE = "all_feedback.csv"
COLUMNS = ["timestamp", "profile_id", "display_name", "page", "message"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit_feedback(message: str, page: str = "", store: ProfileStorage | None = None,
                    display_name: str | None = None) -> None:
    store = store or ProfileStorage()
    name = display_name or st.session_state.get("display_name") or store.profile_id
    row = {
        "timestamp": _now(),
        "profile_id": store.profile_id,
        "display_name": name,
        "page": page,
        "message": message.strip(),
    }
    # Per-user copy (skipped silently if read-only impersonation).
    try:
        store.append_csv("feedback.csv", row)
    except Exception:
        pass
    # Global aggregate is an app-level log, always allowed.
    storage.append_shared_csv(GLOBAL_FILE, row, COLUMNS)


def read_all_feedback():
    return storage.read_shared_csv(GLOBAL_FILE, parse_dates=["timestamp"])


def feedback_count(profile_id: str) -> int:
    df = read_all_feedback()
    if df.empty or "profile_id" not in df.columns:
        return 0
    return int((df["profile_id"] == profile_id).sum())


# ────────────────────────────────────────────────────────────────────────────
# Sidebar widget (rendered on every page)
# ────────────────────────────────────────────────────────────────────────────

def render_sidebar_widget(current_page: str = "") -> None:
    """💬 Send feedback button → dialog with text area + submit."""
    with st.sidebar:
        if st.button("💬 Send feedback", use_container_width=True):
            st.session_state["_show_feedback"] = True

    if st.session_state.get("_show_feedback"):
        _render_dialog(current_page)


def _render_dialog(current_page: str) -> None:
    @st.dialog("Send feedback")  # type: ignore[misc]
    def _dialog() -> None:
        st.write("Tell Ryan what's working, what's broken, or what you'd like to see.")
        msg = st.text_area("Your feedback", key="_feedback_msg", height=140)
        include_ctx = st.checkbox("Include current page context", value=True)
        if st.button("Submit", type="primary"):
            if msg.strip():
                submit_feedback(msg, page=current_page if include_ctx else "")
                st.session_state["_show_feedback"] = False
                st.success("Thanks — feedback sent!")
                st.rerun()
            else:
                st.warning("Please enter some feedback first.")

    _dialog()
