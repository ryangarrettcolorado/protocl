"""Admin · Feedback (owner-only) — spec 1.5.

Aggregated beta feedback, filterable by user, page, and date.
"""
from __future__ import annotations

import streamlit as st

import auth
import feedback as feedback_mod

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

st.title("💬 Beta Feedback")

df = feedback_mod.read_all_feedback()
if df.empty:
    st.info("No feedback submitted yet.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    users = ["(all)"] + sorted(df["display_name"].dropna().unique().tolist())
    who = st.selectbox("User", users)
with c2:
    pages = ["(all)"] + sorted(df["page"].dropna().unique().tolist())
    page = st.selectbox("Page", pages)

view = df.copy()
if who != "(all)":
    view = view[view["display_name"] == who]
if page != "(all)":
    view = view[view["page"] == page]

st.caption(f"{len(view)} message(s)")
st.dataframe(view.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
