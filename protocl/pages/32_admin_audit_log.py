"""Admin · Audit Log (owner-only) — spec 1.6.

Append-only security event log with date + action filters. IPs are stored only
as one-way SHA-256 hashes.
"""
from __future__ import annotations

import streamlit as st

import audit
import auth

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

st.title("📜 Audit Log")

df = audit.read_log()
if df.empty:
    st.info("No audit events recorded yet.")
    st.stop()

c1, c2 = st.columns(2)
with c1:
    actions = ["(all)"] + sorted(df["action"].dropna().unique().tolist())
    action = st.selectbox("Action", actions)
with c2:
    profiles = ["(all)"] + sorted(df["profile_id"].dropna().astype(str).unique().tolist())
    profile = st.selectbox("Profile", profiles)

view = df.copy()
if action != "(all)":
    view = view[view["action"] == action]
if profile != "(all)":
    view = view[view["profile_id"].astype(str) == profile]

st.caption(f"{len(view)} event(s)")
st.dataframe(view.sort_values("timestamp", ascending=False), use_container_width=True, hide_index=True)
