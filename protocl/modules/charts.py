"""Shared Plotly chart builders and design tokens for Protocōl.

All visualizations across pages should pull color tokens and layout defaults
from this module so the brand stays consistent across light and dark modes.

v2 (June 2026): retired the gold/Steelers palette. ``COLORS`` is now derived
from ``modules.theme.BRAND_TOKENS`` and is keyed off the current session
theme mode. Callers that already reference legacy keys (``gold``, ``steel_*``)
still get sensible substitutes so we don't break old chart code in one shot —
those keys are deprecated aliases pointing at the new tokens.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.graph_objects as go

from . import theme as _theme


def _tok(name: str) -> str:
    """Resolve a brand token for the current theme mode."""
    return _theme.token(name)


def _colors_for_mode() -> dict:
    """Build the COLORS dict at call-time, so it follows the theme toggle."""
    return {
        # Canonical names
        "bg":             _tok("bg"),
        "surface":        _tok("surface"),
        "surface_strong": _tok("surface_strong"),
        "border":         _tok("border"),
        "text_primary":   _tok("text"),
        "text_muted":     _tok("muted"),
        "text_faint":     _tok("faint"),
        "primary":        _tok("primary"),
        "primary_soft":   _tok("primary_soft"),
        "success":        _tok("success"),
        "warning":        _tok("warn"),
        "danger":         _tok("danger"),
        # Backward-compat aliases (deprecated)
        "gold":         _tok("primary"),       # legacy accent → primary teal
        "steel_dark":   _tok("bg"),
        "steel_mid":    _tok("surface"),
        "steel_light":  _tok("surface_strong"),
        "steel_border": _tok("border"),
        # Multi-series chart palette (extends primary)
        "chart_series": [
            _tok("c1"), _tok("c2"), _tok("c3"),
            _tok("c4"), _tok("c5"), _tok("c6"),
            _tok("primary_dark"), _tok("primary_mist"),
        ],
    }


class _ColorsProxy:
    """Module-level proxy so ``COLORS["primary"]`` re-resolves each access.

    Plotly traces are usually constructed at request time, but charts that
    *cache* colors at import won't follow the theme switch. Page code should
    re-read ``COLORS["..."]`` on each render — which is the normal pattern.
    """
    def __getitem__(self, key):
        return _colors_for_mode()[key]

    def get(self, key, default=None):
        d = _colors_for_mode()
        return d.get(key, default)

    def __contains__(self, key):
        return key in _colors_for_mode()

    def __iter__(self):
        return iter(_colors_for_mode())

    def keys(self):
        return _colors_for_mode().keys()

    def items(self):
        return _colors_for_mode().items()

    def values(self):
        return _colors_for_mode().values()


COLORS = _ColorsProxy()


def full_height(n_rows: int, *, row_px: int = 35, header_px: int = 38,
                max_px: int = 1200) -> int:
    """Compute a `height=` for `st.dataframe` so every row is visible."""
    n = max(1, int(n_rows))
    return min(header_px + row_px * n, max_px)


def _plotly_layout() -> dict:
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor":  _tok("surface"),
        "font":          {"color": _tok("text"), "family": "Inter, sans-serif"},
        "xaxis":         {"gridcolor": _tok("border"), "linecolor": _tok("border"), "zeroline": False},
        "yaxis":         {"gridcolor": _tok("border"), "linecolor": _tok("border"), "zeroline": False},
        "legend":        {"bgcolor": "rgba(0,0,0,0)", "font": {"color": _tok("text")}},
        "margin":        {"t": 40, "b": 40, "l": 40, "r": 20},
        "hoverlabel":    {"bgcolor": _tok("surface"), "font_color": _tok("text"), "bordercolor": _tok("primary")},
    }


# Backward-compat: tests/code import this name. Provide a property-like object.
class _PlotlyLayoutProxy(dict):
    def __getitem__(self, key):
        return _plotly_layout()[key]

    def __iter__(self):
        return iter(_plotly_layout())

    def get(self, key, default=None):
        return _plotly_layout().get(key, default)

    def keys(self):
        return _plotly_layout().keys()

    def items(self):
        return _plotly_layout().items()

    def __contains__(self, key):
        return key in _plotly_layout()


PLOTLY_LAYOUT = _PlotlyLayoutProxy()


def apply_theme(fig: go.Figure, height: int | None = None) -> go.Figure:
    """Apply the Protocōl base layout to any Plotly figure."""
    layout = _plotly_layout()
    if height is not None:
        layout["height"] = height
    fig.update_layout(**layout)
    return fig


# ────────────────────────────────────────────────────────────────────────────
# Reusable chart factories
# ────────────────────────────────────────────────────────────────────────────

def sparkline(values: Iterable[float], color: str | None = None, height: int = 40) -> go.Figure:
    """A tiny inline sparkline for a single biomarker history."""
    color = color or _tok("primary")
    values = list(values)
    fig = go.Figure(
        go.Scatter(
            x=list(range(len(values))),
            y=values,
            mode="lines",
            line=dict(color=color, width=2),
            hoverinfo="skip",
        )
    )
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def time_series(
    df: pd.DataFrame,
    x: str,
    y: str,
    *,
    title: str | None = None,
    optimal_low: float | None = None,
    optimal_high: float | None = None,
    lab_low: float | None = None,
    lab_high: float | None = None,
    unit: str = "",
    height: int = 360,
    color: str | None = None,
) -> go.Figure:
    """Line chart with optional lab and optimal range bands."""
    color = color or _tok("primary")
    fig = go.Figure()

    if lab_low is not None and lab_high is not None:
        fig.add_hrect(
            y0=lab_low, y1=lab_high,
            fillcolor=_tok("muted_soft") if False else "rgba(160,160,160,0.10)",
            line_width=0,
            annotation_text="Lab range",
            annotation_position="top left",
            annotation_font_color=_tok("muted"),
        )
    if optimal_low is not None and optimal_high is not None:
        fig.add_hrect(
            y0=optimal_low, y1=optimal_high,
            fillcolor=_tok("primary_soft"),
            line_width=0,
            annotation_text="Optimal",
            annotation_position="bottom left",
            annotation_font_color=_tok("primary"),
        )

    fig.add_trace(go.Scatter(
        x=df[x], y=df[y],
        mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=7, color=color, line=dict(color=_tok("bg"), width=1)),
        name=y,
        hovertemplate=f"%{{x|%b %d, %Y}}<br><b>%{{y}}</b> {unit}<extra></extra>",
    ))

    apply_theme(fig, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=16, color=_tok("text"))))
    fig.update_yaxes(title_text=unit or None)
    return fig


def status_color(value: float, optimal_low: float | None, optimal_high: float | None,
                 lab_low: float | None, lab_high: float | None) -> str:
    """Return a status color tag: success / warning / danger."""
    if pd.isna(value):
        return _tok("muted")
    if lab_low is not None and lab_high is not None:
        if value < lab_low or value > lab_high:
            return _tok("danger")
    if optimal_low is not None and optimal_high is not None:
        if optimal_low <= value <= optimal_high:
            return _tok("success")
        return _tok("warn")
    return _tok("muted")


def status_label(value: float, optimal_low: float | None, optimal_high: float | None,
                 lab_low: float | None, lab_high: float | None) -> str:
    """Return Optimal / Monitor / Risk / Unknown."""
    if pd.isna(value):
        return "Unknown"
    if lab_low is not None and lab_high is not None:
        if value < lab_low or value > lab_high:
            return "Risk"
    if optimal_low is not None and optimal_high is not None:
        if optimal_low <= value <= optimal_high:
            return "Optimal"
        return "Monitor"
    return "Unknown"


def status_badge_html(label: str) -> str:
    """Render a status as an inline HTML badge."""
    cls = {
        "Optimal": "badge-optimal",
        "Monitor": "badge-monitor",
        "Risk":    "badge-risk",
        "Unknown": "badge-unknown",
    }.get(label, "badge-unknown")
    return f'<span class="{cls}">{label}</span>'


def tier_badge_html(tier: str) -> str:
    """Render a confidence tier as an inline HTML badge."""
    tier = (tier or "").upper().replace("TIER ", "").strip()
    cls = {"T1": "tier-t1", "T2": "tier-t2", "T3": "tier-t3", "T4": "tier-t4", "T5": "tier-t5"}.get(tier, "tier-t5")
    return f'<span class="{cls}">Tier {tier}</span>'


def metric_card_html(label: str, value: str, delta: str | None = None,
                     delta_positive: bool | None = None) -> str:
    """Render a KPI card as raw HTML (use with st.markdown(..., unsafe_allow_html=True))."""
    delta_html = ""
    if delta is not None:
        cls = "metric-delta-pos" if delta_positive else "metric-delta-neg"
        delta_html = f'<div class="{cls}">{delta}</div>'
    return (
        '<div class="metric-card">'
        f'<div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div>'
        f'{delta_html}'
        '</div>'
    )
