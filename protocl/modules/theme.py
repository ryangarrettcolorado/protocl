"""Shared theme injection — call inject_css() at the top of every page.

Streamlit renders each page as its own document, so CSS injected in app.py
does NOT cascade to pages/*.py. This module centralizes the CSS so we can
keep it in one place and call it from each page's setup block.

v2.0 (June 2026) — Brand rebrand:
- Identity: TEAL on cream (light) / TEAL on near-black (dark).
- See docs/BRAND.md for the canonical token contract.
- All component CSS reads tokens via CSS custom properties (`var(--brand-*)`)
  so light/dark mode can be flipped at runtime by setting
  `body[data-theme="dark"]` (default: light).
- Python callers that need a hex value should import `BRAND_TOKENS` and look
  up by name + mode.

v1.5 additions kept intact:
- ``render_top_brand`` — slim brand bar above the top nav (replaces sidebar brand).
- ``.section-group-header`` + ``.section-status-chip-row`` — collapsible
  group headers used by the single-page-grouped layout.
- ``.sticky-filter-bar`` — sticky page-local filter bar.
- ``.density-compact`` / ``.density-comfortable`` — body-level density.
- ``.home-row`` — consistent vertical spacing between Home dashboard rows.
- ``.alert-chip-*`` — Row 2 banner chips.
- ``.timeline-event-row`` — Row 5 event list styling.

``render_sidebar_brand`` is kept as a no-op alias.
"""
from __future__ import annotations

import streamlit as st


# ─── Brand tokens (Python-side mirror of CSS custom properties) ──────────────
# Keep these in sync with the :root / [data-theme=dark] blocks in CUSTOM_CSS
# and with docs/BRAND.md. Python callers that need a concrete hex (e.g. for a
# Plotly trace) should use BRAND_TOKENS[mode][token].

BRAND_TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "bg":             "#F7F6F2",
        "surface":        "#F9F8F5",
        "surface_strong": "#EFEDE6",
        "border":         "#D4D1CA",
        "border_strong":  "#B9B5AC",
        "text":           "#28251D",
        "muted":          "#7A7974",
        "faint":          "#BAB9B4",
        "primary":        "#01696F",
        "primary_dark":   "#0C4E54",
        "primary_mist":   "#BCE2E7",
        "primary_soft":   "rgba(1,105,111,0.08)",
        "success":        "#2E7D5B",
        "warn":           "#B5651D",
        "danger":         "#A8341E",
        "info":           "#01696F",
        # Chart palette
        "c1": "#20808D", "c2": "#A84B2F", "c3": "#1B474D",
        "c4": "#BCE2E7", "c5": "#944454", "c6": "#FFC553",
    },
    "dark": {
        "bg":             "#0C1E20",
        "surface":        "#152A2D",
        "surface_strong": "#0F2326",
        "border":         "rgba(60,180,190,0.20)",
        "border_strong":  "rgba(60,180,190,0.40)",
        "text":           "#E8E5DA",
        "muted":          "#A0A8A8",
        "faint":          "#6C7475",
        "primary":        "#3CB4BE",
        "primary_dark":   "#01696F",
        "primary_mist":   "#BCE2E7",
        "primary_soft":   "rgba(60,180,190,0.18)",
        "success":        "#4CAF50",
        "warn":           "#FF9800",
        "danger":         "#F44336",
        "info":           "#3CB4BE",
        # Chart palette — same teal-scheme order but brightened where needed
        "c1": "#3CB4BE", "c2": "#FFAB91", "c3": "#80DEEA",
        "c4": "#BCE2E7", "c5": "#F48FB1", "c6": "#FFD54F",
    },
}


def get_theme_mode() -> str:
    """Return the user's current theme mode: 'light' (default) or 'dark'."""
    return st.session_state.get("theme_mode", "light")


def token(name: str, *, mode: str | None = None) -> str:
    """Look up a brand token's concrete value for the current (or given) mode.

    Use this in Python contexts that can't consume CSS variables, e.g. Plotly
    trace colors. UI CSS should use ``var(--brand-NAME)`` instead.
    """
    m = mode or get_theme_mode()
    if m not in BRAND_TOKENS:
        m = "light"
    return BRAND_TOKENS[m].get(name, BRAND_TOKENS[m]["text"])


# ─── CSS ─────────────────────────────────────────────────────────────────────
# All component CSS uses var(--brand-*) so flipping data-theme on <body>
# re-skins everything without re-injecting CSS.

CUSTOM_CSS = """
<style>
/* ── Token contract ────────────────────────────────────────────────────── */
:root, body[data-theme="light"] {
    --brand-bg:             #F7F6F2;
    --brand-surface:        #F9F8F5;
    --brand-surface-strong: #EFEDE6;
    --brand-border:         #D4D1CA;
    --brand-border-strong:  #B9B5AC;
    --brand-text:           #28251D;
    --brand-muted:          #7A7974;
    --brand-faint:          #BAB9B4;
    --brand-primary:        #01696F;
    --brand-primary-dark:   #0C4E54;
    --brand-primary-mist:   #BCE2E7;
    --brand-primary-soft:   rgba(1,105,111,0.08);
    --brand-success:        #2E7D5B;
    --brand-warn:           #B5651D;
    --brand-danger:         #A8341E;
    --brand-success-soft:   rgba(46,125,91,0.14);
    --brand-warn-soft:      rgba(181,101,29,0.14);
    --brand-danger-soft:    rgba(168,52,30,0.14);
    --brand-muted-soft:     rgba(122,121,116,0.14);
}
body[data-theme="dark"] {
    --brand-bg:             #0C1E20;
    --brand-surface:        #152A2D;
    --brand-surface-strong: #0F2326;
    --brand-border:         rgba(60,180,190,0.20);
    --brand-border-strong:  rgba(60,180,190,0.40);
    --brand-text:           #E8E5DA;
    --brand-muted:          #A0A8A8;
    --brand-faint:          #6C7475;
    --brand-primary:        #3CB4BE;
    --brand-primary-dark:   #01696F;
    --brand-primary-mist:   #BCE2E7;
    --brand-primary-soft:   rgba(60,180,190,0.18);
    --brand-success:        #4CAF50;
    --brand-warn:           #FF9800;
    --brand-danger:         #F44336;
    --brand-success-soft:   rgba(76,175,80,0.18);
    --brand-warn-soft:      rgba(255,152,0,0.18);
    --brand-danger-soft:    rgba(244,67,54,0.18);
    --brand-muted-soft:     rgba(160,168,168,0.18);
    background-color: var(--brand-bg);
    color: var(--brand-text);
}
body[data-theme="dark"] .stApp,
body[data-theme="dark"] [data-testid="stAppViewContainer"],
body[data-theme="dark"] [data-testid="stHeader"] {
    background-color: var(--brand-bg) !important;
    color: var(--brand-text);
}
body[data-theme="dark"], body[data-theme="dark"] p,
body[data-theme="dark"] li, body[data-theme="dark"] span,
body[data-theme="dark"] h1, body[data-theme="dark"] h2,
body[data-theme="dark"] h3, body[data-theme="dark"] h4 {
    color: var(--brand-text);
}

/* ── Base ──────────────────────────────────────────────────────────────── */
.block-container { padding-top: 1.5rem; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* ── Top brand bar (replaces sidebar brand) ────────────────────────────── */
/* The brand-row wrapper holds the brand on the left and the theme toggle
   pill on the right in a single border-bottomed band. Streamlit columns
   render right after this marker div, so we target them by sibling. */
.protocl-top-brand-row {
    margin: 2.5rem -1rem 0;
    padding: 0 1rem;
    border-bottom: 1px solid var(--brand-border);
}
.protocl-top-brand-row + div[data-testid="stHorizontalBlock"] {
    margin: 0 -1rem 1.5rem;
    padding: 0 1rem;
    align-items: center;
}
.protocl-top-brand-row + div[data-testid="stHorizontalBlock"]
  > div[data-testid="stColumn"]:last-child {
    display: flex;
    align-items: center;
    justify-content: flex-end;
}
.protocl-top-brand-row + div[data-testid="stHorizontalBlock"]
  div[data-testid="stButton"] > button {
    background: var(--brand-surface);
    color: var(--brand-text);
    border: 1px solid var(--brand-border);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 0.85rem;
    font-weight: 500;
    min-height: 0;
    line-height: 1.2;
    transition: background 120ms ease, color 120ms ease, border-color 120ms ease;
}
.protocl-top-brand-row + div[data-testid="stHorizontalBlock"]
  div[data-testid="stButton"] > button:hover {
    background: var(--brand-primary);
    color: #fff;
    border-color: var(--brand-primary);
}
.protocl-top-brand {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 22px 0 20px;
}
.protocl-mark {
    flex: 0 0 auto;
    width: 48px;
    height: 48px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
}
body[data-theme="dark"] .protocl-mark {
    filter: drop-shadow(0 0 12px rgba(60,180,190,0.25));
}
.protocl-mark svg { width: 100%; height: 100%; display: block; }
.protocl-mark svg path,
.protocl-mark svg circle { stroke: var(--brand-primary); }
.protocl-mark svg circle { fill: var(--brand-primary); stroke: none; }
.protocl-brand-stack {
    display: flex;
    flex-direction: column;
    gap: 2px;
    line-height: 1.1;
}
.protocl-brand {
    color: var(--brand-primary);
    font-weight: 800;
    font-size: 2.35rem;
    letter-spacing: -0.005em;
    line-height: 1;
}
.protocl-tagline {
    color: var(--brand-muted);
    font-size: 0.92rem;
    font-style: italic;
    letter-spacing: 0.01em;
}
@media (max-width: 640px) {
    .protocl-mark { width: 38px; height: 38px; }
    .protocl-brand { font-size: 1.7rem; }
    .protocl-tagline { font-size: 0.8rem; }
}

/* ── KPI metric cards ──────────────────────────────────────────────────── */
.metric-card {
    background: var(--brand-surface);
    border: 1px solid var(--brand-border);
    border-radius: 8px;
    padding: 16px 14px;
    text-align: center;
    height: 100%;
}
.metric-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--brand-primary);
    font-variant-numeric: tabular-nums;
    line-height: 1.15;
}
.metric-label {
    font-size: 0.72rem;
    color: var(--brand-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 6px;
}
.metric-delta-pos { color: var(--brand-success); font-size: 0.85rem; margin-top: 4px; }
.metric-delta-neg { color: var(--brand-danger);  font-size: 0.85rem; margin-top: 4px; }

/* ── Status / tier badges ──────────────────────────────────────────────── */
.badge-optimal { background: var(--brand-success-soft); color: var(--brand-success); border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-monitor { background: var(--brand-warn-soft);    color: var(--brand-warn);    border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-risk    { background: var(--brand-danger-soft);  color: var(--brand-danger);  border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-unknown { background: var(--brand-muted-soft);   color: var(--brand-muted);   border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }

.tier-t1 { color: var(--brand-success); font-weight: 600; }
.tier-t2 { color: var(--brand-success); font-weight: 600; opacity: 0.85; }
.tier-t3 { color: var(--brand-primary); font-weight: 600; }
.tier-t4 { color: var(--brand-warn);    font-weight: 600; }
.tier-t5 { color: var(--brand-muted);   font-weight: 600; }

/* ── Cards ─────────────────────────────────────────────────────────────── */
.risk-card {
    background: var(--brand-surface);
    border: 1px solid var(--brand-border);
    border-left: 3px solid var(--brand-warn);
    border-radius: 6px;
    padding: 14px 16px;
    margin-bottom: 10px;
    color: var(--brand-text);
}
.risk-card-high { border-left-color: var(--brand-danger); }
.risk-card-low  { border-left-color: var(--brand-muted); }

.rec-card {
    background: var(--brand-surface);
    border: 1px solid var(--brand-border);
    border-left: 3px solid var(--brand-primary);
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
    color: var(--brand-text);
}
.rec-card-title { color: var(--brand-primary); font-weight: 700; font-size: 1.05rem; margin-bottom: 6px; }

/* ── Section group headers (single-page-grouped layout) ────────────────── */
.section-group-header {
    color: var(--brand-primary);
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: 0.01em;
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
}
.section-group-header .section-group-icon { font-size: 1.1rem; }
.section-group-header .section-group-count {
    color: var(--brand-muted);
    font-weight: 500;
    font-size: 0.82rem;
}
.section-status-chip-row {
    display: inline-flex;
    gap: 6px;
    margin-left: 6px;
}
.section-status-chip-row .badge-monitor,
.section-status-chip-row .badge-risk,
.section-status-chip-row .badge-optimal,
.section-status-chip-row .badge-unknown {
    font-size: 0.68rem;
    padding: 1px 6px;
}

/* ── Sticky filter bar ─────────────────────────────────────────────────── */
.sticky-filter-bar {
    position: sticky;
    top: 0;
    z-index: 50;
    background: color-mix(in srgb, var(--brand-bg) 92%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--brand-border);
    padding: 8px 4px;
    margin: 0 0 14px;
}

/* ── Home dashboard rows ───────────────────────────────────────────────── */
.home-row { margin-bottom: 1.25rem; }
.home-row h2, .home-row h3 {
    margin-top: 0.25rem;
    margin-bottom: 0.75rem;
}

/* ── Alert chips (Home Row 2 banner) ───────────────────────────────────── */
.alert-chip-high     { background: var(--brand-danger-soft);  color: var(--brand-danger);  border: 1px solid var(--brand-danger);  border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 600; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-chip-monitor  { background: var(--brand-warn-soft);    color: var(--brand-warn);    border: 1px solid var(--brand-warn);    border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 600; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-chip-resolved { background: var(--brand-muted-soft);   color: var(--brand-muted);   border: 1px solid var(--brand-border-strong); border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 500; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-banner-nominal {
    background: var(--brand-success-soft);
    border: 1px solid var(--brand-success);
    color: var(--brand-success);
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 0.92rem;
}

/* ── Timeline event rows (Home Row 5) ──────────────────────────────────── */
.timeline-event-row {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--brand-border);
    font-size: 0.92rem;
}
.timeline-event-row:last-child { border-bottom: 0; }
.timeline-event-icon  { font-size: 1.1rem; width: 1.6rem; text-align: center; }
.timeline-event-date  { color: var(--brand-muted); font-variant-numeric: tabular-nums; min-width: 70px; }
.timeline-event-text  { color: var(--brand-text); flex: 1; }

/* ── Density modifiers ─────────────────────────────────────────────────── */
.density-compact .metric-card     { padding: 10px 10px; }
.density-compact .metric-value    { font-size: 1.6rem; }
.density-compact .rec-card        { padding: 12px; }
.density-compact .risk-card       { padding: 10px 12px; }
.density-compact .timeline-event-row { padding: 6px 10px; }
.density-comfortable              { /* default — no overrides */ }

/* ── Tables / Streamlit chrome ─────────────────────────────────────────── */
body[data-theme="dark"] [data-testid="stDataFrame"] { background: var(--brand-surface); }

.stButton > button {
    background: var(--brand-surface);
    color: var(--brand-primary);
    border: 1px solid var(--brand-primary);
    border-radius: 6px;
    font-weight: 600;
}
.stButton > button:hover {
    background: var(--brand-primary);
    border-color: var(--brand-primary);
    color: var(--brand-bg);
}

section[data-testid="stSidebar"] {
    background: var(--brand-surface-strong);
    border-right: 1px solid var(--brand-border);
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>

<script>
/* Re-apply the data-theme attribute every time CSS is injected, in case a
   prior page render reset the body. */
(function() {
    const root = window.parent && window.parent.document
        ? window.parent.document.body
        : document.body;
    if (!root) return;
    // The Streamlit app sets the desired mode by also injecting a tiny
    // <meta name="protocl-theme" content="dark"> tag right before this CSS.
    const meta = (window.parent && window.parent.document)
        ? window.parent.document.querySelector('meta[name="protocl-theme"]')
        : document.querySelector('meta[name="protocl-theme"]');
    const mode = meta ? meta.getAttribute('content') : 'light';
    root.setAttribute('data-theme', mode === 'dark' ? 'dark' : 'light');
})();
</script>
"""


# Bump this whenever CSS changes shape so we can prove server-side which build
# is live (the value is also shown by the freshness badge on Home).
UI_VERSION = "2.0.0"
UI_BUILD_LABEL = "v2.0 · teal-on-cream · light+dark · token-driven"


def inject_css() -> None:
    """Inject the Protocōl CSS. Idempotent — call once per page near the top.

    Also writes a `<meta name="protocl-theme">` tag based on the current
    session theme mode so the inline JS in CUSTOM_CSS can set the body's
    `data-theme` attribute.
    """
    mode = get_theme_mode()
    marker = (
        f'<!-- protocl ui={UI_VERSION} mode={mode} build="{UI_BUILD_LABEL}" -->'
        f'<meta name="protocl-theme" content="{mode}">'
    )
    st.markdown(marker + CUSTOM_CSS, unsafe_allow_html=True)


def render_top_brand(tagline: str = "Precision data. Confident decisions. Verified outcomes.") -> None:
    """Render the Protocōl brand bar with a right-aligned theme switcher.

    Streamlit renders ``st.navigation`` once per session at the entry point,
    so this needs to be called from ``app.py`` (not from individual pages).
    Uses ``st.columns`` so the toggle button is a real Streamlit control
    (not an unreachable HTML element) and can mutate session_state on click.
    """
    # Custom inline SVG mark (Chevron Shield). Strokes are colored by CSS
    # (.protocl-mark svg path { stroke: var(--brand-primary) }), so we use
    # currentColor as a fallback in case the CSS hasn't loaded yet.
    mark_svg = (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" '
        'aria-hidden="true" role="img">'
        '<path d="M32 4 L56 12 L56 32 Q56 50 32 60 Q8 50 8 32 L8 12 Z" '
        'fill="none" stroke="currentColor" stroke-width="2.5" stroke-linejoin="round"/>'
        '<path d="M18 44 L32 30 L46 44" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4"/>'
        '<path d="M18 36 L32 22 L46 36" fill="none" stroke="currentColor" '
        'stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.7"/>'
        '<path d="M18 28 L32 14 L46 28" fill="none" stroke="currentColor" '
        'stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>'
        '<circle cx="32" cy="14" r="2.8" fill="currentColor"/>'
        '</svg>'
    )

    # Two-column header: brand on the left, theme switcher pill on the right.
    # The header CSS (.protocl-top-brand-row) flattens column padding so the
    # toggle button lines up with the brand text baseline.
    st.markdown('<div class="protocl-top-brand-row">', unsafe_allow_html=True)
    col_brand, col_toggle = st.columns([6, 1], gap="small")
    with col_brand:
        st.markdown(
            f'<div class="protocl-top-brand">'
            f'<span class="protocl-mark" style="color: var(--brand-primary);">{mark_svg}</span>'
            f'<span class="protocl-brand-stack">'
            f'<span class="protocl-brand">Protocōl</span>'
            f'<span class="protocl-tagline">{tagline}</span>'
            f'</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with col_toggle:
        render_theme_toggle(key="theme_mode_header")
    st.markdown('</div>', unsafe_allow_html=True)


def render_theme_toggle(*, key: str = "theme_mode_toggle") -> None:
    """Render a single-click Light↔Dark switcher pill.

    Stores the chosen mode in ``st.session_state["theme_mode"]`` and triggers
    a rerun so the CSS can re-inject with the new mode marker. Designed to be
    placed in the header (see ``render_top_brand``), but safe to call anywhere.
    """
    current = get_theme_mode()
    # Show the icon for the mode you'd switch TO (affordance: "click here to
    # go dark" when light, "click here to go light" when dark).
    next_mode = "dark" if current == "light" else "light"
    icon = "🌙" if next_mode == "dark" else "☀️"
    label = f"{icon} {next_mode.capitalize()}"
    help_text = f"Switch to {next_mode} mode"
    if st.button(label, key=key, help=help_text, use_container_width=True):
        st.session_state["theme_mode"] = next_mode
        st.rerun()


def render_sidebar_brand() -> None:
    """Deprecated in v1.5 — kept as a no-op for backward-compat."""
    return None


def apply_density(density: str) -> None:
    """Wrap the page in a density class so CSS overrides take effect."""
    cls = "density-compact" if density == "compact" else "density-comfortable"
    st.markdown(
        f'<div class="{cls}" id="protocl-density-root"></div>',
        unsafe_allow_html=True,
    )


def render_section_header(icon: str, title: str, count_text: str = "",
                          chips_html: str = "") -> None:
    """Render a section header for a collapsible group inside ``st.expander``."""
    chip_block = f'<span class="section-status-chip-row">{chips_html}</span>' if chips_html else ""
    count_block = f'<span class="section-group-count">{count_text}</span>' if count_text else ""
    st.markdown(
        f'<div class="section-group-header">'
        f'<span class="section-group-icon">{icon}</span>'
        f'<span>{title}</span>'
        f'{count_block}'
        f'{chip_block}'
        f'</div>',
        unsafe_allow_html=True,
    )


def grouped_sections(labels: list[str], *, expanded: bool | list[bool] = True):
    """Drop-in replacement for ``st.tabs(labels)`` that returns collapsible
    ``st.expander`` containers instead — one per label.

    Each label may begin with an emoji/icon followed by a space; we split that
    off and pass it to ``render_section_header`` so users see iconography
    above each expander.

    Returns: list of expander context managers in the same order as ``labels``.
    """
    if isinstance(expanded, bool):
        expanded_flags = [expanded] * len(labels)
    else:
        expanded_flags = list(expanded) + [True] * (len(labels) - len(expanded))

    containers = []
    for label, exp in zip(labels, expanded_flags):
        icon, title = "", label
        if label and " " in label:
            first, rest = label.split(" ", 1)
            if len(first) <= 3 and not first.isalnum():
                icon, title = first, rest
        if not icon:
            icon = "•"
        render_section_header(icon, title)
        containers.append(st.expander(title, expanded=exp))
    return containers
