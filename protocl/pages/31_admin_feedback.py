"""Admin · Feedback (owner-only) — v3.6 structured feedback triage.

Sentiment breakdown over time, TF-IDF top-complaint clustering (no LLM),
and per-message event context. Filterable by sentiment, page, user, and date.
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

import auth
from modules import feedback_v2
from modules.theme import inject_css

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

inject_css()

st.title("💬 Beta Feedback")
st.caption("Structured feedback (v3.6). Sentiment trend, top complaints, and context.")

df = feedback_v2.read_all_feedback()
if df.empty:
    st.info("No feedback submitted yet.")
    st.stop()

# Old (v3.2) rows have no sentiment — treat as unclassified for charts.
if "sentiment" not in df.columns:
    df["sentiment"] = ""

# ── Filters ──────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
with c1:
    sentiments = ["(all)"] + list(feedback_v2.SENTIMENTS)
    pick_sent = st.selectbox("Sentiment", sentiments)
with c2:
    users = ["(all)"] + sorted(df["display_name"].dropna().unique().tolist())
    who = st.selectbox("User", users)
with c3:
    pages = ["(all)"] + sorted(df["page"].dropna().astype(str).unique().tolist())
    page = st.selectbox("Page", pages)

view = df.copy()
if pick_sent != "(all)":
    view = view[view["sentiment"] == pick_sent]
if who != "(all)":
    view = view[view["display_name"] == who]
if page != "(all)":
    view = view[view["page"].astype(str) == page]

st.caption(f"{len(view)} message(s)")

# ── Sentiment breakdown by week ───────────────────────────────────────────────
st.subheader("Sentiment over time")
ts = pd.to_datetime(view["timestamp"], errors="coerce", utc=True)
classified = view[ts.notna() & view["sentiment"].isin(feedback_v2.SENTIMENTS)].copy()
if classified.empty:
    st.caption("No classified sentiment in the current filter.")
else:
    classified["week"] = (
        pd.to_datetime(classified["timestamp"], errors="coerce", utc=True)
        .dt.tz_convert("UTC").dt.to_period("W").apply(lambda p: p.start_time.date())
    )
    pivot = (
        classified.groupby(["week", "sentiment"]).size().unstack(fill_value=0)
        .reindex(columns=list(feedback_v2.SENTIMENTS), fill_value=0)
        .sort_index()
    )
    st.bar_chart(pivot)

# ── TF-IDF top complaints (negative + mixed) ─────────────────────────────────
st.subheader("Top complaint terms")
st.caption("Ranked by TF-IDF across negative + mixed feedback (no AI).")
gripe = view[view["sentiment"].isin(("negative", "mixed"))]
texts: list[str] = []
for col in ("improvement", "expected", "message"):
    if col in gripe.columns:
        texts.extend(gripe[col].dropna().astype(str).tolist())
terms = feedback_v2.top_complaint_terms(texts, top_n=12)
if not terms:
    st.caption("Not enough negative/mixed text to cluster yet.")
else:
    term_df = pd.DataFrame(terms, columns=["term", "weight"]).set_index("term")
    st.bar_chart(term_df)

# ── Per-message detail with event context ────────────────────────────────────
st.divider()
st.subheader("Messages")
for _, row in view.sort_values("timestamp", ascending=False).iterrows():
    sent = str(row.get("sentiment") or "")
    label = feedback_v2.SENTIMENT_LABELS.get(sent, "—")
    name = row.get("display_name") or row.get("profile_id") or "?"
    pg = row.get("page") or ""
    header = f"{label} · {name} · {pg or '(no page)'} · {row.get('timestamp')}"
    with st.expander(header, expanded=False):
        if str(row.get("expected") or "").strip():
            st.markdown(f"**Expected:** {row['expected']}")
        if str(row.get("improvement") or "").strip():
            st.markdown(f"**Improvement:** {row['improvement']}")
        if str(row.get("message") or "").strip():
            st.markdown(f"**More:** {row['message']}")
        recent = row.get("recent_events")
        if isinstance(recent, str) and recent.strip():
            try:
                parsed = json.loads(recent)
                if parsed:
                    st.caption("Recent events leading up to this:")
                    st.json(parsed)
            except (ValueError, TypeError):
                pass
