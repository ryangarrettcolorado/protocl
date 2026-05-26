"""Shared theme injection — call inject_css() at the top of every page.

Streamlit renders each page as its own document, so CSS injected in app.py
does NOT cascade to pages/*.py. This module centralizes the CSS so we can
keep it in one place and call it from each page's setup block.
"""
from __future__ import annotations

import streamlit as st


CUSTOM_CSS = """
<style>
.block-container { padding-top: 2rem; }

h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* KPI metric cards */
.metric-card {
    background: #1C1C1C;
    border: 1px solid rgba(255,182,18,0.18);
    border-radius: 8px;
    padding: 16px 14px;
    text-align: center;
    height: 100%;
    box-shadow: 0 1px 0 rgba(255,182,18,0.05) inset;
}
.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: #FFB612;
    font-variant-numeric: tabular-nums;
    line-height: 1.15;
}
.metric-label {
    font-size: 0.72rem;
    color: #A0A0A0;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}
.metric-delta-pos { color: #4CAF50; font-size: 0.85rem; margin-top: 4px; }
.metric-delta-neg { color: #F44336; font-size: 0.85rem; margin-top: 4px; }

/* Status badges */
.badge-optimal { background: rgba(76,175,80,0.18); color: #4CAF50; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-monitor { background: rgba(255,152,0,0.18); color: #FF9800; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-risk    { background: rgba(244,67,54,0.18); color: #F44336; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-unknown { background: rgba(160,160,160,0.18); color: #A0A0A0; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }

.tier-t1 { color: #4CAF50; font-weight: 600; }
.tier-t2 { color: #8BC34A; font-weight: 600; }
.tier-t3 { color: #FFB612; font-weight: 600; }
.tier-t4 { color: #FF9800; font-weight: 600; }
.tier-t5 { color: #A0A0A0; font-weight: 600; }

.risk-card {
    background: #1C1C1C;
    border-left: 3px solid #FF9800;
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
}

.rec-card {
    background: #1C1C1C;
    border: 1px solid rgba(255,182,18,0.20);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}
.rec-card-title { color: #FFB612; font-weight: 600; font-size: 1.05rem; margin-bottom: 6px; }

section[data-testid="stSidebar"] { background: #1C1C1C; border-right: 1px solid rgba(255,182,18,0.10); }

[data-testid="stDataFrame"] { background: #1C1C1C; }

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

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

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


def inject_css() -> None:
    """Inject the Protocōl CSS. Idempotent — call once per page near the top."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_sidebar_brand() -> None:
    """Render the Protocōl brand mark in the sidebar."""
    with st.sidebar:
        st.markdown(
            '<div class="protocl-brand">⚗️ Protocōl</div>'
            '<div class="protocl-tagline">Your data. Your protocol. Your proof.</div>',
            unsafe_allow_html=True,
        )
        st.divider()
