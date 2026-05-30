"""Admin · LLM Costs (owner-only) — spec 2.7.

Per-user spend, per-tier token usage, and the per-app daily budget status.
"""
from __future__ import annotations

import streamlit as st

import auth
from explainers import rate_limit

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

st.title("💸 LLM Cost Dashboard")

remaining = rate_limit.app_budget_remaining()
st.metric("App budget remaining today", f"{remaining} / {rate_limit.APP_DAILY_LIMIT} calls")
if remaining <= 0:
    st.warning("Daily LLM budget reached — Tier 2/3 are disabled; Tier 1 remains available.")

df = rate_limit.read_cost_log()
if df.empty:
    st.info("No LLM cost events logged yet.")
    st.stop()

total = float(df["estimated_cost_usd"].sum())
st.metric("Estimated total spend (logged)", f"${total:,.4f}")

st.subheader("By user")
by_user = (df.groupby("profile_id")
             .agg(calls=("tier", "count"),
                  prompt_tokens=("prompt_tokens", "sum"),
                  completion_tokens=("completion_tokens", "sum"),
                  cost_usd=("estimated_cost_usd", "sum"))
             .reset_index())
st.dataframe(by_user, use_container_width=True, hide_index=True)

st.subheader("Recent calls")
st.dataframe(df.sort_values("timestamp", ascending=False).head(200),
             use_container_width=True, hide_index=True)
