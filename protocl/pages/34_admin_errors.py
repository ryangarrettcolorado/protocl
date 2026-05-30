"""Admin · Errors (owner-only) — v3.5 error monitoring."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

import auth
from modules import error_capture
from modules.theme import inject_css

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

inject_css()

st.title("🐞 Errors")
st.caption("Captured in-app errors, deduplicated by traceback. Last 30 days.")

df = error_capture.read_errors()
if df.empty:
    st.success("No errors captured. 🎉")
    st.stop()

cutoff = pd.Timestamp(datetime.now(timezone.utc) - timedelta(days=30))
ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
df = df[ts >= cutoff]

fixed = error_capture.fixed_hashes()

st.subheader("Top errors by frequency (24h)")
grouped = error_capture.group_by_hash(since_hours=24)
if grouped.empty:
    st.caption("No errors in the last 24 hours.")
else:
    for _, row in grouped.iterrows():
        th = str(row["traceback_hash"])
        is_fixed = th in fixed
        c1, c2 = st.columns([6, 1])
        with c1:
            tag = " ✅ fixed" if is_fixed else ""
            st.markdown(
                f"**{row['exception_type']}** · {int(row['count'])}× · "
                f"last {row['last_seen']}{tag}"
            )
            st.caption(f"`{th}` — {row['message']}")
        with c2:
            if not is_fixed and st.button("Mark fixed", key=f"fix_{th}"):
                error_capture.mark_fixed(th)
                st.rerun()

st.divider()
st.subheader("All errors (30 days)")
st.dataframe(
    df.sort_values("timestamp", ascending=False),
    use_container_width=True,
    hide_index=True,
)
