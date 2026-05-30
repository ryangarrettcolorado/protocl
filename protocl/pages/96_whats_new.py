"""v3.5 — What's New (in-app changelog). Visiting marks all versions seen."""
from __future__ import annotations

import streamlit as st

import auth
from modules import changelog, events
from modules.theme import inject_css
from storage import ProfileStorage

auth.require_auth()
inject_css()

store = ProfileStorage()

st.title("📣 What's New")
st.caption("Recent changes to Protocōl.")

versions = changelog.parse_changelog()
if not versions:
    st.info("No changelog entries yet.")
    st.stop()

# Mark seen + record the visit (only writes for non-read-only sessions).
if not st.session_state.get("read_only"):
    changelog.mark_seen(store)
events.track("page_view", page="whats_new", store=store)

version_labels = [v.version for v in versions]
chosen = st.multiselect(
    "Filter by version",
    options=version_labels,
    default=version_labels,
    key="_changelog_filter",
)

for v in versions:
    if chosen and v.version not in chosen:
        continue
    header = f"### {v.version}" + (f" — {v.date}" if v.date else "")
    st.markdown(header)
    for section, items in v.sections.items():
        if not items:
            continue
        st.markdown(f"**{section}**")
        for it in items:
            st.markdown(f"- {it}")
    st.divider()
