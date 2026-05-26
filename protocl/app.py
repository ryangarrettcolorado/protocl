"""Protocōl — Health Intelligence OS.

Entry point. Streamlit's multipage convention loads pages/*.py automatically;
this file holds the global theme, custom CSS, and the landing splash that
shows when the user first lands on the root.
"""
from __future__ import annotations

import streamlit as st

from modules.data_loader import load_data
from modules.theme import inject_css, render_sidebar_brand


st.set_page_config(
    page_title="Protocōl — Health Intelligence OS",
    page_icon="⚗️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ────────────────────────────────────────────────────────────────────────────
# Global custom CSS — Steelers theme tokens applied across all pages.
# CSS lives in modules/theme.py so every page can inject the same styles.
# ────────────────────────────────────────────────────────────────────────────

inject_css()
render_sidebar_brand()

# (the inline CSS block below is kept for reference but no longer used)
_LEGACY_CSS = """
<style>
/* Tighter top spacing */
.block-container { padding-top: 2rem; }

/* Headings */
h1, h2, h3, h4 { letter-spacing: -0.01em; }
h1 { color: #F0F0F0; font-weight: 700; }

/* KPI metric cards */
.metric-card {
    background: #1C1C1C;
    border: 1px solid rgba(255,182,18,0.15);
    border-radius: 8px;
    padding: 16px;
    text-align: center;
    height: 100%;
}
.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #FFB612;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
}
.metric-label {
    font-size: 0.72rem;
    color: #A0A0A0;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 4px;
}
.metric-delta-pos { color: #4CAF50; font-size: 0.875rem; margin-top: 4px; }
.metric-delta-neg { color: #F44336; font-size: 0.875rem; margin-top: 4px; }

/* Status badges */
.badge-optimal { background: rgba(76,175,80,0.15);  color: #4CAF50; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-monitor { background: rgba(255,152,0,0.15);  color: #FF9800; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-risk    { background: rgba(244,67,54,0.15);  color: #F44336; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-unknown { background: rgba(160,160,160,0.15); color: #A0A0A0; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }

/* Confidence tier badges */
.tier-t1 { color: #4CAF50; font-weight: 600; }
.tier-t2 { color: #8BC34A; font-weight: 600; }
.tier-t3 { color: #FFB612; font-weight: 600; }
.tier-t4 { color: #FF9800; font-weight: 600; }
.tier-t5 { color: #A0A0A0; font-weight: 600; }

/* Risk and recommendation cards */
.risk-card {
    background: #1C1C1C;
    border-left: 3px solid #FF9800;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
}
.risk-card-high { border-left-color: #F44336; }
.risk-card-low  { border-left-color: #A0A0A0; }

.rec-card {
    background: #1C1C1C;
    border: 1px solid rgba(255,182,18,0.20);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}
.rec-card-title { color: #FFB612; font-weight: 600; font-size: 1.05rem; margin-bottom: 6px; }

/* Sidebar nav */
section[data-testid="stSidebar"] {
    background: #1C1C1C;
    border-right: 1px solid rgba(255,182,18,0.10);
}
section[data-testid="stSidebar"] .stRadio > label { font-size: 0.95rem; }

/* Tables */
[data-testid="stDataFrame"] { background: #1C1C1C; }

/* Buttons */
.stButton > button {
    background: #1C1C1C;
    color: #FFB612;
    border: 1px solid rgba(255,182,18,0.30);
    border-radius: 6px;
    font-weight: 500;
}
.stButton > button:hover {
    background: rgba(255,182,18,0.10);
    border-color: #FFB612;
    color: #FFB612;
}

/* Hide Streamlit chrome */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

/* Brand mark */
.protocl-brand {
    color: #FFB612;
    font-weight: 800;
    font-size: 1.25rem;
    letter-spacing: 0.02em;
    margin-bottom: 0.25rem;
}
.protocl-tagline { color: #A0A0A0; font-size: 0.78rem; font-style: italic; margin-bottom: 1rem; }
</style>
"""



# ────────────────────────────────────────────────────────────────────────────
# Landing splash (only visible on app.py — pages render their own content)
# ────────────────────────────────────────────────────────────────────────────

st.title("Protocōl")
st.caption("Health Intelligence OS — personal performance + longevity command center")

# Quick health snapshot KPIs so the home page is immediately useful
data = load_data()

col1, col2, col3, col4 = st.columns(4)
with col1:
    bw = data.bloodwork
    last_date = bw["date"].max() if not bw.empty else None
    days_ago = (st.session_state.get("today_iso") or None)
    if last_date is not None:
        import pandas as pd
        days = (pd.Timestamp("2026-05-25") - last_date).days
        st.markdown(
            f'<div class="metric-card"><div class="metric-label">Last Bloodwork</div>'
            f'<div class="metric-value">{days}d</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="metric-card"><div class="metric-label">Last Bloodwork</div>'
            '<div class="metric-value">—</div></div>',
            unsafe_allow_html=True,
        )
with col2:
    active = data.protocol[data.protocol["end_date"].isna()] if not data.protocol.empty else None
    n = len(active) if active is not None else 0
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">Active Protocol Items</div>'
        f'<div class="metric-value">{n}</div></div>',
        unsafe_allow_html=True,
    )
with col3:
    open_actions = data.action_items[data.action_items["status"].isin(["open", "in_progress"])] if not data.action_items.empty else None
    n = len(open_actions) if open_actions is not None else 0
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">Open Action Items</div>'
        f'<div class="metric-value">{n}</div></div>',
        unsafe_allow_html=True,
    )
with col4:
    active_exps = [e for e in data.nof1_experiments if e.get("status") == "active"]
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">Active N=1</div>'
        f'<div class="metric-value">{len(active_exps)}</div></div>',
        unsafe_allow_html=True,
    )

st.markdown("")
st.markdown(
    "Use the sidebar to navigate to **Overview** for your full snapshot, "
    "**Protocol** to manage active interventions, or **Bloodwork** to dive into the lab data."
)

with st.expander("About Protocōl"):
    st.markdown("""
**Protocōl** is your personal health intelligence OS — a self-directed tracking and analysis tool
for supplements, hormones, peptides, bloodwork, CGM, body composition, training, and wearable data.

Reference ranges throughout the app reflect **functional medicine and longevity research consensus**,
not standard-of-care lab normals. Every range is cited and tagged with a confidence tier so you can
form your own conclusions.

This is a tool for personal health sovereignty, not a medical device or diagnostic tool. See Settings
for the full disclaimer.
    """)
