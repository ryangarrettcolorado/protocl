"""Shared theme injection — call inject_css() at the top of every page.

Streamlit renders each page as its own document, so CSS injected in app.py
does NOT cascade to pages/*.py. This module centralizes the CSS so we can
keep it in one place and call it from each page's setup block.

v1.5 additions:
- ``render_top_brand`` — slim brand bar above the top nav (replaces sidebar brand).
- ``.section-group-header`` + ``.section-status-chip-row`` — collapsible
  group headers used by the single-page-grouped layout.
- ``.sticky-filter-bar`` — sticky page-local filter bar.
- ``.density-compact`` / ``.density-comfortable`` — body-level density.
- ``.home-row`` — consistent vertical spacing between Home dashboard rows.
- ``.alert-chip-*`` — Row 2 banner chips.
- ``.timeline-event-row`` — Row 5 event list styling.

``render_sidebar_brand`` is kept as a no-op alias so any straggler imports
don't crash during the v1.5 migration.
"""
from __future__ import annotations

import streamlit as st


CUSTOM_CSS = """
<style>
/* ── Base ──────────────────────────────────────────────────────────────── */
.block-container { padding-top: 1.5rem; }

h1, h2, h3, h4 { letter-spacing: -0.01em; }

/* ── Top brand bar (replaces sidebar brand) ────────────────────────────── */
.protocl-top-brand {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 22px 1rem 20px;
    border-bottom: 1px solid rgba(255,182,18,0.14);
    /* Streamlit's deploy/share toolbar sits ~36px tall in the top-right.
       Push the brand down enough that it never tucks under it. */
    margin: 2.5rem -1rem 1.5rem;
}
.protocl-mark {
    flex: 0 0 auto;
    width: 48px;
    height: 48px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    filter: drop-shadow(0 0 12px rgba(255,182,18,0.25));
}
.protocl-mark svg { width: 100%; height: 100%; display: block; }
.protocl-brand-stack {
    display: flex;
    flex-direction: column;
    gap: 2px;
    line-height: 1.1;
}
.protocl-brand {
    color: #FFB612;
    font-weight: 800;
    font-size: 2.35rem;
    letter-spacing: 0.005em;
    line-height: 1;
}
.protocl-tagline {
    color: #B8B8B8;
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

/* ── Status / tier badges ──────────────────────────────────────────────── */
.badge-optimal { background: rgba(76,175,80,0.18); color: #4CAF50; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-monitor { background: rgba(255,152,0,0.18); color: #FF9800; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-risk    { background: rgba(244,67,54,0.18); color: #F44336; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }
.badge-unknown { background: rgba(160,160,160,0.18); color: #A0A0A0; border-radius: 4px; padding: 2px 8px; font-size: 0.72rem; font-weight: 600; }

.tier-t1 { color: #4CAF50; font-weight: 600; }
.tier-t2 { color: #8BC34A; font-weight: 600; }
.tier-t3 { color: #FFB612; font-weight: 600; }
.tier-t4 { color: #FF9800; font-weight: 600; }
.tier-t5 { color: #A0A0A0; font-weight: 600; }

/* ── Cards ─────────────────────────────────────────────────────────────── */
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

/* ── Section group headers (single-page-grouped layout) ────────────────── */
.section-group-header {
    color: #FFB612;
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
    color: #A0A0A0;
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
    background: rgba(16,16,16,0.92);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(255,182,18,0.10);
    padding: 8px 4px;
    margin: 0 0 14px;
}

/* ── Home dashboard rows ───────────────────────────────────────────────── */
.home-row {
    margin-bottom: 1.25rem;
}
.home-row h2, .home-row h3 {
    margin-top: 0.25rem;
    margin-bottom: 0.75rem;
}

/* ── Alert chips (Home Row 2 banner) ───────────────────────────────────── */
.alert-chip-high     { background: rgba(244,67,54,0.18); color: #F44336; border: 1px solid rgba(244,67,54,0.35); border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 600; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-chip-monitor  { background: rgba(255,152,0,0.18); color: #FF9800; border: 1px solid rgba(255,152,0,0.35); border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 600; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-chip-resolved { background: rgba(160,160,160,0.18); color: #A0A0A0; border: 1px solid rgba(160,160,160,0.35); border-radius: 16px; padding: 4px 12px; font-size: 0.78rem; font-weight: 500; display: inline-block; margin-right: 6px; margin-bottom: 6px; }
.alert-banner-nominal {
    background: rgba(76,175,80,0.12);
    border: 1px solid rgba(76,175,80,0.30);
    color: #4CAF50;
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
    border-bottom: 1px solid rgba(255,182,18,0.07);
    font-size: 0.92rem;
}
.timeline-event-row:last-child { border-bottom: 0; }
.timeline-event-icon  { font-size: 1.1rem; width: 1.6rem; text-align: center; }
.timeline-event-date  { color: #A0A0A0; font-variant-numeric: tabular-nums; min-width: 70px; }
.timeline-event-text  { color: #F0F0F0; flex: 1; }

/* ── Density modifiers ─────────────────────────────────────────────────── */
.density-compact .metric-card     { padding: 10px 10px; }
.density-compact .metric-value    { font-size: 1.6rem; }
.density-compact .rec-card        { padding: 12px; }
.density-compact .risk-card       { padding: 10px 12px; }
.density-compact .timeline-event-row { padding: 6px 10px; }
.density-comfortable              { /* default — no overrides */ }

/* ── Tables / Streamlit chrome ─────────────────────────────────────────── */
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

section[data-testid="stSidebar"] { background: #1C1C1C; border-right: 1px solid rgba(255,182,18,0.10); }

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
"""


def inject_css() -> None:
    """Inject the Protocōl CSS. Idempotent — call once per page near the top."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def render_top_brand(tagline: str = "Your data. Your protocol. Your proof.") -> None:
    """Render the Protocōl brand bar above the top nav.

    Streamlit renders ``st.navigation`` once per session at the entry point,
    so this needs to be called from ``app.py`` (not from individual pages).
    """
    # Custom inline SVG mark: hexagonal molecular node (data + biology) with
    # an inner double-helix curve. Echoes the macron-O in "Protocōl".
    mark_svg = (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" '
        'aria-hidden="true" role="img">'
        # outer hexagon
        '<path d="M32 3.5 L57 17.75 L57 46.25 L32 60.5 L7 46.25 L7 17.75 Z" '
        'fill="none" stroke="#FFB612" stroke-width="2.5" stroke-linejoin="round"/>'
        # inner ring (data node)
        '<circle cx="32" cy="32" r="6" fill="#FFB612"/>'
        # helix-style arcs through the node
        '<path d="M16 22 Q32 32 48 22" fill="none" stroke="#FFB612" '
        'stroke-width="2" stroke-linecap="round" opacity="0.85"/>'
        '<path d="M16 42 Q32 32 48 42" fill="none" stroke="#FFB612" '
        'stroke-width="2" stroke-linecap="round" opacity="0.85"/>'
        # vertex accents
        '<circle cx="32" cy="3.5" r="1.8" fill="#FFB612"/>'
        '<circle cx="32" cy="60.5" r="1.8" fill="#FFB612"/>'
        '</svg>'
    )
    st.markdown(
        f'<div class="protocl-top-brand">'
        f'<span class="protocl-mark">{mark_svg}</span>'
        f'<span class="protocl-brand-stack">'
        f'<span class="protocl-brand">Protocōl</span>'
        f'<span class="protocl-tagline">{tagline}</span>'
        f'</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


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
    """Render a section header for a collapsible group inside ``st.expander``.

    Use directly above (or as the first child of) an ``st.expander`` so the
    user sees the icon + count + status chips before they collapse the group.
    """
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
    Usage:
        sections = grouped_sections(["❤️ Cardiovascular", "🩸 Glucose"])
        with sections[0]:
            ...
        with sections[1]:
            ...
    """
    if isinstance(expanded, bool):
        expanded_flags = [expanded] * len(labels)
    else:
        expanded_flags = list(expanded) + [True] * (len(labels) - len(expanded))

    containers = []
    for label, exp in zip(labels, expanded_flags):
        # Try to split off a leading icon (one or two non-space tokens then a space)
        icon, title = "", label
        if label and " " in label:
            first, rest = label.split(" ", 1)
            # Treat the first token as an icon if it's short and non-alphanumeric-heavy
            if len(first) <= 3 and not first.isalnum():
                icon, title = first, rest
        if not icon:
            icon = "•"
        render_section_header(icon, title)
        containers.append(st.expander(title, expanded=exp))
    return containers
