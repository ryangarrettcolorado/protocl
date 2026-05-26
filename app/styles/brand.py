"""Protocōl brand & design system injector for Streamlit.

Reads /design/protocol.tokens.json and injects:
  - Google Fonts (Inter + JetBrains Mono)
  - CSS custom properties for color, radius, space, motion, type
  - Component overrides for buttons, metrics, inputs, tabs, sidebar, dataframes,
    and st.success/info/warning/error containers.

Usage (in app.py):

    import streamlit as st
    from app.styles.brand import inject_brand_css, render_header

    st.set_page_config(
        page_title="Protocōl — Personal Health Intelligence OS",
        page_icon="assets/protocol-icon.svg",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_brand_css()
    render_header()
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

TOKENS_PATH = Path(__file__).resolve().parents[2] / "design" / "protocol.tokens.json"


def _load_tokens() -> dict[str, Any]:
    with TOKENS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _v(node: dict[str, Any]) -> Any:
    """Return a token's `value` field."""
    return node["value"]


def _build_css(tokens: dict[str, Any]) -> str:
    c = tokens["color"]
    r = tokens["radius"]
    s = tokens["space"]
    m = tokens["motion"]
    t = tokens["type"]
    e = tokens["elevation"]

    css_vars = f"""
    :root {{
      --color-bg:           {_v(c['bg']['default'])};
      --color-bg-subtle:    {_v(c['bg']['subtle'])};
      --color-bg-muted:     {_v(c['bg']['muted'])};
      --color-bg-inverse:   {_v(c['bg']['inverse'])};
      --color-bg-elevated:  {_v(c['bg']['elevated'])};

      --color-text:         {_v(c['text']['default'])};
      --color-text-muted:   {_v(c['text']['muted'])};
      --color-text-inverse: {_v(c['text']['inverse'])};
      --color-text-accent:  {_v(c['text']['accent'])};

      --color-brand:        {_v(c['brand']['primary'])};
      --color-accent:       {_v(c['brand']['accent'])};
      --color-info:         {_v(c['signal']['info'])};
      --color-success:      {_v(c['state']['success'])};
      --color-warning:      {_v(c['state']['warning'])};
      --color-error:        {_v(c['state']['error'])};
      --color-border:       {_v(c['border']['subtle'])};

      --radius-sm:   {_v(r['sm'])}px;
      --radius-md:   {_v(r['md'])}px;
      --radius-lg:   {_v(r['lg'])}px;
      --radius-xl:   {_v(r['xl'])}px;
      --radius-pill: {_v(r['pill'])}px;

      --space-1: {_v(s['1'])}px;
      --space-2: {_v(s['2'])}px;
      --space-3: {_v(s['3'])}px;
      --space-4: {_v(s['4'])}px;
      --space-5: {_v(s['5'])}px;
      --space-6: {_v(s['6'])}px;
      --space-7: {_v(s['7'])}px;
      --space-8: {_v(s['8'])}px;

      --elevation-1: {_v(e['1'])};
      --elevation-2: {_v(e['2'])};

      --motion-fast: {_v(m['duration']['fast'])};
      --motion-base: {_v(m['duration']['base'])};
      --motion-slow: {_v(m['duration']['slow'])};
      --easing-standard:   {_v(m['easing']['standard'])};
      --easing-emphasized: {_v(m['easing']['emphasized'])};

      --font-ui:   {_v(t['family']['ui'])};
      --font-mono: {_v(t['family']['mono'])};
    }}
    """

    component_css = """
    html, body, [class*="css"], .stApp {
      font-family: var(--font-ui);
      color: var(--color-text);
      background: var(--color-bg);
    }
    h1, h2, h3, h4 {
      color: var(--color-text);
      letter-spacing: -0.01em;
      font-weight: 600;
    }
    h1 { font-size: 32px; line-height: 1.2; }
    h2 { font-size: 24px; line-height: 1.25; }
    h3 { font-size: 18px; line-height: 1.3; }
    p, li, label, span { color: var(--color-text); }
    small, .stCaption, [data-testid="stCaptionContainer"] { color: var(--color-text-muted); }

    section[data-testid="stSidebar"] {
      background: var(--color-bg-subtle);
      border-right: 1px solid var(--color-border);
    }

    .stButton > button, .stDownloadButton > button {
      border-radius: var(--radius-lg);
      border: 1px solid var(--color-border);
      background: var(--color-bg-elevated);
      color: var(--color-text);
      font-weight: 600;
      padding: 10px 18px;
      transition: all var(--motion-base) var(--easing-standard);
      box-shadow: var(--elevation-1);
    }
    .stButton > button:hover { box-shadow: var(--elevation-2); transform: translateY(-1px); }
    .stButton > button[kind="primary"] {
      background: var(--color-brand);
      color: var(--color-text-inverse);
      border-color: var(--color-brand);
    }
    .stButton > button[kind="primary"]:hover { background: #2A2E33; }

    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stNumberInput input,
    .stSelectbox div[data-baseweb="select"] > div {
      background: var(--color-bg-elevated) !important;
      border-radius: var(--radius-md) !important;
      border: 1px solid var(--color-border) !important;
      color: var(--color-text) !important;
    }

    [data-testid="stMetric"] {
      background: var(--color-bg-elevated);
      padding: var(--space-5);
      border-radius: var(--radius-lg);
      border: 1px solid var(--color-border);
      box-shadow: var(--elevation-1);
    }
    [data-testid="stMetricValue"] { color: var(--color-text); font-weight: 700; }
    [data-testid="stMetricDelta"] { color: var(--color-success); font-weight: 600; }

    .stTabs [data-baseweb="tab-list"] { gap: var(--space-2); }
    .stTabs [data-baseweb="tab"] {
      background: transparent; border-radius: var(--radius-pill);
      padding: 6px 14px; color: var(--color-text-muted); font-weight: 500;
    }
    .stTabs [aria-selected="true"] {
      background: var(--color-brand); color: var(--color-text-inverse);
    }

    [data-testid="stAlert"] {
      border-radius: var(--radius-md);
      border: 1px solid var(--color-border);
      box-shadow: var(--elevation-1);
    }

    [data-testid="stDataFrame"] {
      border-radius: var(--radius-md);
      border: 1px solid var(--color-border);
      overflow: hidden;
    }

    .protocol-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: var(--space-4) 0 var(--space-5) 0;
      border-bottom: 1px solid var(--color-border);
      margin-bottom: var(--space-6);
    }
    .protocol-header .left { display: flex; align-items: center; gap: var(--space-3); }
    .protocol-header .wordmark {
      font-family: var(--font-ui); font-weight: 700; font-size: 28px;
      color: var(--color-text); letter-spacing: -0.02em;
    }
    .protocol-header .tagline {
      color: var(--color-accent); font-style: italic; font-size: 14px;
    }
    .protocol-header .icon {
      width: 36px; height: 36px; border-radius: 10px; background: var(--color-brand);
      color: var(--color-accent); display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 22px;
    }
    """

    fonts = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap');
    """

    return f"<style>{fonts}{css_vars}{component_css}</style>"


def inject_brand_css() -> None:
    """Inject the Protocōl design system CSS into the current Streamlit page."""
    tokens = _load_tokens()
    st.markdown(_build_css(tokens), unsafe_allow_html=True)


def render_header(tagline: str | None = None) -> None:
    """Render the standard Protocōl page header."""
    tokens = _load_tokens()
    line = tagline or _v(tokens["brand"]["tagline"])
    st.markdown(
        f"""
        <div class="protocol-header">
          <div class="left">
            <div class="icon">P</div>
            <div class="wordmark">Protoc&#333;l</div>
          </div>
          <div class="tagline">{line}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
