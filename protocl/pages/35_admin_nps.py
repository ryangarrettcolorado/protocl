"""Admin · NPS (owner-only) — v3.6 satisfaction tracking."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
from modules import nps
from modules.theme import inject_css

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

inject_css()

st.title("📈 NPS")
st.caption("Net Promoter Score from the in-app micro-survey (sessions 7 / 30 / 60).")

s = nps.summary()
if s["n"] == 0:
    st.info("No NPS responses yet.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("NPS", s["nps"])
c2.metric("Promoters", s["promoters"])
c3.metric("Passives", s["passives"])
c4.metric("Detractors", s["detractors"])
st.caption(f"Based on the latest response from each of {s['n']} respondent(s).")

df = nps.read_responses()

st.subheader("Score distribution")
counts = (
    df["score"].dropna().astype(int).value_counts()
    .reindex(range(0, 11), fill_value=0).sort_index()
)
st.bar_chart(counts)

st.subheader("Responses over time")
df = df.copy()
df["bucket"] = df["score"].dropna().astype(int).map(nps.categorize)
ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
df = df[ts.notna()]
df["week"] = pd.to_datetime(df["timestamp"], utc=True).dt.to_period("W").apply(
    lambda p: p.start_time.date()
)
trend = (
    df.groupby(["week", "bucket"]).size().unstack(fill_value=0)
    .reindex(columns=["detractor", "passive", "promoter"], fill_value=0).sort_index()
)
st.bar_chart(trend)

st.divider()
st.subheader("Verbatims")
with_reason = df[df["reason"].astype(str).str.strip() != ""]
if with_reason.empty:
    st.caption("No written reasons yet.")
else:
    for _, r in with_reason.sort_values("timestamp", ascending=False).iterrows():
        st.markdown(f"**{int(r['score'])}** ({r['bucket']}) — {r['reason']}")
        st.caption(str(r["timestamp"]))
