"""Admin · Analytics (owner-only) — v3.6 learning-loop dashboard.

Four tabs: Engagement · Funnel health · Feedback pulse · Drop-off watchlist.
Engagement uses the ANONYMIZED daily rollup (no profile_id). Funnel + watchlist
read per-user state via read-only ProfileStorage. No LLM.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
from modules import analytics, events, feedback_v2, nps
from modules.theme import inject_css

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

inject_css()

st.title("📊 Analytics")
st.caption("Learning-loop dashboard. Engagement is fully anonymized.")

tab_eng, tab_funnel, tab_fb, tab_drop = st.tabs(
    ["Engagement", "Funnel health", "Feedback pulse", "Drop-off watchlist"]
)

# ── Engagement ───────────────────────────────────────────────────────────────
with tab_eng:
    rollup = events.read_rollup()
    if rollup.empty:
        st.info("No analytics yet. Events appear once users browse with analytics on.")
    else:
        dau = analytics.daily_active(rollup)
        wau = analytics.weekly_active(rollup)
        st.subheader("Daily active (session starts)")
        if dau.empty:
            st.caption("No sessions recorded.")
        else:
            st.line_chart(dau.set_index("date"))
        st.subheader("Weekly active")
        if wau.empty:
            st.caption("No sessions recorded.")
        else:
            st.bar_chart(wau.set_index("week"))
        st.subheader("Top pages")
        tp = analytics.top_pages(rollup)
        if tp.empty:
            st.caption("No page views recorded.")
        else:
            st.bar_chart(tp.set_index("page"))

# ── Funnel health ────────────────────────────────────────────────────────────
with tab_funnel:
    f = analytics.funnel_counts()
    st.subheader("Onboarding funnel")
    stages = [
        ("Signed up", f["signed_up"]),
        ("Consented", f["consented"]),
        ("First data", f["first_data"]),
        ("Returned (3rd visit)", f["returned"]),
    ]
    cols = st.columns(len(stages))
    top = max((v for _, v in stages), default=0) or 1
    for col, (label, val) in zip(cols, stages):
        col.metric(label, val)
    fdf = pd.DataFrame(stages, columns=["stage", "count"]).set_index("stage")
    st.bar_chart(fdf)
    st.caption(
        "Drop between adjacent bars is where users stall — focus onboarding "
        "fixes on the steepest cliff."
    )

# ── Feedback pulse ───────────────────────────────────────────────────────────
with tab_fb:
    df = feedback_v2.read_all_feedback()
    st.subheader("Sentiment mix")
    if df.empty or "sentiment" not in df.columns:
        st.caption("No structured feedback yet.")
    else:
        counts = (
            df[df["sentiment"].isin(feedback_v2.SENTIMENTS)]["sentiment"]
            .value_counts().reindex(list(feedback_v2.SENTIMENTS), fill_value=0)
        )
        if counts.sum() == 0:
            st.caption("No classified sentiment yet.")
        else:
            st.bar_chart(counts)
        gripe = df[df["sentiment"].isin(("negative", "mixed"))]
        texts: list[str] = []
        for c in ("improvement", "expected", "message"):
            if c in gripe.columns:
                texts.extend(gripe[c].dropna().astype(str).tolist())
        terms = feedback_v2.top_complaint_terms(texts, top_n=10)
        st.subheader("Top complaint terms")
        if terms:
            st.bar_chart(pd.DataFrame(terms, columns=["term", "weight"]).set_index("term"))
        else:
            st.caption("Not enough negative/mixed text to cluster.")

    st.subheader("NPS")
    s = nps.summary()
    if s["n"] == 0:
        st.caption("No NPS responses yet.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("NPS", s["nps"])
        c2.metric("Promoters", s["promoters"])
        c3.metric("Passives", s["passives"])
        c4.metric("Detractors", s["detractors"])
    st.page_link("pages/35_admin_nps.py", label="Full NPS breakdown", icon="📈")

# ── Drop-off watchlist ───────────────────────────────────────────────────────
with tab_drop:
    st.subheader("Inactive users (≥ 7 days)")
    wl = analytics.dropoff_watchlist(min_days=7)
    if wl.empty:
        st.success("No users are currently inactive. 🎉")
    else:
        for _, r in wl.iterrows():
            pid = str(r["profile_id"])
            c1, c2 = st.columns([4, 1])
            with c1:
                st.markdown(f"**{pid}** — {r['days_inactive']:.0f} days inactive")
            with c2:
                if st.button("Send check-in", key=f"checkin_{pid}"):
                    import owner_inbox
                    from modules import user_prefs, dropoff
                    from storage import ProfileStorage as _PS
                    _s = _PS()
                    _s.profile_id = pid
                    _s.read_only = False
                    user_prefs.set_value("dropoff_nudge", dropoff.NUDGE_MESSAGE, _s)
                    owner_inbox.add(f"Manual check-in queued for {pid}.", kind="dropoff")
                    st.success(f"Check-in nudge queued for {pid}.")
