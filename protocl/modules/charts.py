"""Shared Plotly chart builders and design tokens for Protocōl.

All visualizations across pages should pull color tokens and layout defaults
from this module so the Pittsburgh Steelers theme stays consistent.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd
import plotly.graph_objects as go


COLORS = {
    "gold":         "#FFB612",
    "steel_dark":   "#101010",
    "steel_mid":    "#1C1C1C",
    "steel_light":  "#2A2A2A",
    "steel_border": "rgba(255,182,18,0.15)",
    "text_primary": "#F0F0F0",
    "text_muted":   "#A0A0A0",
    "text_faint":   "#666666",
    "success":      "#4CAF50",
    "warning":      "#FF9800",
    "danger":       "#F44336",
    "chart_series": ["#FFB612", "#4FC3F7", "#81C784", "#FF8A65", "#CE93D8", "#80DEEA"],
}


PLOTLY_LAYOUT: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor":  "rgba(28,28,28,1)",
    "font":          {"color": "#F0F0F0", "family": "Inter, sans-serif"},
    "xaxis":         {"gridcolor": "#2A2A2A", "linecolor": "#2A2A2A", "zeroline": False},
    "yaxis":         {"gridcolor": "#2A2A2A", "linecolor": "#2A2A2A", "zeroline": False},
    "legend":        {"bgcolor": "rgba(0,0,0,0)"},
    "margin":        {"t": 40, "b": 40, "l": 40, "r": 20},
    "hoverlabel":    {"bgcolor": "#1C1C1C", "font_color": "#F0F0F0", "bordercolor": "#FFB612"},
}


def apply_theme(fig: go.Figure, height: int | None = None) -> go.Figure:
    """Apply the Protocōl base layout to any Plotly figure."""
    layout = dict(PLOTLY_LAYOUT)
    if height is not None:
        layout["height"] = height
    fig.update_layout(**layout)
    return fig


# ────────────────────────────────────────────────────────────────────────────
# Reusable chart factories
# ────────────────────────────────────────────────────────────────────────────

def sparkline(values: Iterable[float], color: str | None = None, height: int = 40) -> go.Figure:
    """A tiny inline sparkline for a single biomarker history."""
    color = color or COLORS["gold"]
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
    color = color or COLORS["gold"]
    fig = go.Figure()

    if lab_low is not None and lab_high is not None:
        fig.add_hrect(
            y0=lab_low, y1=lab_high,
            fillcolor="rgba(160,160,160,0.10)",
            line_width=0,
            annotation_text="Lab range",
            annotation_position="top left",
            annotation_font_color=COLORS["text_muted"],
        )
    if optimal_low is not None and optimal_high is not None:
        fig.add_hrect(
            y0=optimal_low, y1=optimal_high,
            fillcolor="rgba(255,182,18,0.12)",
            line_width=0,
            annotation_text="Optimal",
            annotation_position="bottom left",
            annotation_font_color=COLORS["gold"],
        )

    fig.add_trace(go.Scatter(
        x=df[x], y=df[y],
        mode="lines+markers",
        line=dict(color=color, width=2),
        marker=dict(size=7, color=color, line=dict(color=COLORS["steel_dark"], width=1)),
        name=y,
        hovertemplate=f"%{{x|%b %d, %Y}}<br><b>%{{y}}</b> {unit}<extra></extra>",
    ))

    apply_theme(fig, height=height)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=16, color=COLORS["text_primary"])))
    fig.update_yaxes(title_text=unit or None)
    return fig


def status_color(value: float, optimal_low: float | None, optimal_high: float | None,
                 lab_low: float | None, lab_high: float | None) -> str:
    """Return a status color tag: success / warning / danger."""
    if pd.isna(value):
        return COLORS["text_muted"]
    if lab_low is not None and lab_high is not None:
        if value < lab_low or value > lab_high:
            return COLORS["danger"]
    if optimal_low is not None and optimal_high is not None:
        if optimal_low <= value <= optimal_high:
            return COLORS["success"]
        return COLORS["warning"]
    return COLORS["text_muted"]


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
