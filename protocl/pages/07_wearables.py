"""Wearables — RHR, HRV, sleep, respiratory rate, SpO2, skin temp, steps."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data
from modules.charts import COLORS, apply_theme, metric_card_html, full_height


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Wearables")
    st.caption("Recovery signals · sleep architecture · autonomic balance")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.wearables.copy()

if df.empty:
    st.info("No wearable data logged yet.")
    st.stop()

df = df.sort_values("date").reset_index(drop=True)

TODAY = pd.Timestamp("2026-05-25")
last_7 = df[df["date"] >= TODAY - pd.Timedelta(days=7)]
last_28 = df[df["date"] >= TODAY - pd.Timedelta(days=28)]
prev_28 = df[(df["date"] >= TODAY - pd.Timedelta(days=56)) & (df["date"] < TODAY - pd.Timedelta(days=28))]

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
rhr_7 = last_7["resting_hr_bpm"].mean()
rhr_baseline = df["resting_hr_bpm"].head(14).mean()
rhr_delta = rhr_7 - rhr_baseline

hrv_7 = last_7["hrv_sdnn_ms"].mean()
hrv_baseline = df["hrv_sdnn_ms"].head(14).mean()
hrv_delta = hrv_7 - hrv_baseline

sleep_7 = last_7["sleep_duration_hrs"].mean()
deep_7 = last_7["sleep_deep_hrs"].mean()
rem_7 = last_7["sleep_rem_hrs"].mean()
spo2_7 = last_7["spo2_pct"].mean()
steps_7 = last_7["steps"].mean()

kpis = [
    ("RESTING HR", f"{rhr_7:.0f} bpm", f"{rhr_delta:+.1f} vs baseline", rhr_delta < 0),
    ("HRV (SDNN)", f"{hrv_7:.0f} ms", f"{hrv_delta:+.1f} vs baseline", hrv_delta > 0),
    ("SLEEP", f"{sleep_7:.1f} h", "7d avg", sleep_7 >= 7.5),
    ("DEEP SLEEP", f"{deep_7:.1f} h", "target ≥1.5h", deep_7 >= 1.5),
    ("SpO2", f"{spo2_7:.1f}%", "target ≥95%", spo2_7 >= 95),
    ("STEPS", f"{steps_7:,.0f}", "daily avg", steps_7 >= 8000),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_recovery, tab_sleep, tab_activity, tab_table = grouped_sections(
    ["💓 Recovery", "🌙 Sleep", "🚶 Activity", "📋 Raw Data"]
)

# ── Recovery (RHR + HRV) ────────────────────────────────────────────────────
with tab_recovery:
    st.subheader("Resting HR + HRV — 90 Day Trend")

    # Restrict to the trailing 90 days so the rolling lines aren't crushed by years of history.
    recov_cutoff = TODAY - pd.Timedelta(days=90)
    df_recov = df[df["date"] >= recov_cutoff].copy().sort_values("date")
    if df_recov.empty:
        df_recov = df.sort_values("date").tail(90).copy()
    df_recov["rhr_7d"] = df_recov["resting_hr_bpm"].rolling(7, min_periods=2).mean()
    df_recov["hrv_7d"] = df_recov["hrv_sdnn_ms"].rolling(7, min_periods=2).mean()
    hrv_median = float(df_recov["hrv_sdnn_ms"].median()) if df_recov["hrv_sdnn_ms"].notna().any() else None

    fig = go.Figure()
    # Faint raw daily traces as background
    fig.add_trace(go.Scatter(
        x=df_recov["date"], y=df_recov["resting_hr_bpm"],
        mode="lines", name="RHR daily",
        line=dict(color=COLORS["chart_series"][3], width=1),
        opacity=0.3,
        yaxis="y",
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df_recov["date"], y=df_recov["rhr_7d"],
        mode="lines", name="RHR (7d avg)",
        line=dict(color=COLORS["chart_series"][3], width=2.5),
        yaxis="y",
        hovertemplate="%{x|%b %d}<br>RHR 7d %{y:.0f} bpm<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_recov["date"], y=df_recov["hrv_sdnn_ms"],
        mode="lines", name="HRV daily",
        line=dict(color=COLORS["chart_series"][0], width=1),
        opacity=0.3,
        yaxis="y2",
        showlegend=False,
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=df_recov["date"], y=df_recov["hrv_7d"],
        mode="lines", name="HRV (7d avg)",
        line=dict(color=COLORS["chart_series"][0], width=2.5),
        yaxis="y2",
        hovertemplate="%{x|%b %d}<br>HRV 7d %{y:.0f} ms<extra></extra>",
    ))
    if hrv_median is not None:
        fig.add_hline(
            y=hrv_median, yref="y2",
            line=dict(color=COLORS["chart_series"][0], width=1, dash="dash"),
            opacity=0.55,
            annotation_text=f"HRV Baseline ({hrv_median:.0f} ms, 90d median)",
            annotation_position="bottom right",
            annotation_font_color=COLORS["chart_series"][0],
        )
    apply_theme(fig, height=440)
    fig.update_layout(
        yaxis=dict(title="RHR (bpm)", gridcolor="#2A2A2A"),
        yaxis2=dict(title="HRV SDNN (ms)", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Lines show 7-day rolling average. Faint background = raw daily values. "
               "Dashed line = 90-day median HRV (your baseline).")

    # Respiratory rate + skin temp delta — illness early warning
    st.subheader("Illness Early Warning — RR & Skin Temp Δ")
    fig_warn = go.Figure()
    fig_warn.add_trace(go.Scatter(
        x=df["date"], y=df["respiratory_rate_brpm"],
        mode="lines", name="Respiratory Rate",
        line=dict(color=COLORS["chart_series"][2], width=2),
    ))
    fig_warn.add_trace(go.Scatter(
        x=df["date"], y=df["skin_temp_delta_f"],
        mode="lines", name="Skin Temp Δ°F",
        line=dict(color=COLORS["warning"], width=2),
        yaxis="y2",
    ))
    apply_theme(fig_warn, height=300)
    fig_warn.update_layout(
        yaxis=dict(title="brpm"),
        yaxis2=dict(title="°F delta", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    st.plotly_chart(fig_warn, use_container_width=True)
    st.caption("Sustained jumps in RR + skin temp 1-3 days = early illness signal.")

# ── Sleep ───────────────────────────────────────────────────────────────────
with tab_sleep:
    st.subheader("Sleep Duration + Architecture")

    fig = go.Figure()
    df["light"] = df["sleep_duration_hrs"] - df["sleep_deep_hrs"] - df["sleep_rem_hrs"]
    fig.add_trace(go.Bar(
        x=df["date"], y=df["sleep_deep_hrs"],
        name="Deep", marker=dict(color=COLORS["chart_series"][4]),
    ))
    fig.add_trace(go.Bar(
        x=df["date"], y=df["sleep_rem_hrs"],
        name="REM", marker=dict(color=COLORS["chart_series"][1]),
    ))
    fig.add_trace(go.Bar(
        x=df["date"], y=df["light"],
        name="Light", marker=dict(color=COLORS["chart_series"][5]),
    ))
    fig.update_layout(barmode="stack")
    fig.add_hline(y=7.5, line=dict(color=COLORS["text_primary"], width=1, dash="dash"),
                  annotation_text="7.5h target", annotation_position="right")
    apply_theme(fig, height=380)
    fig.update_layout(
        yaxis=dict(title="Hours"),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Sleep consistency
    st.subheader("Sleep Consistency")
    fig_cons = go.Figure()
    fig_cons.add_trace(go.Scatter(
        x=df["date"], y=df["sleep_consistency_pct"],
        mode="lines", name="Consistency %",
        line=dict(color=COLORS["gold"], width=3),
        fill="tozeroy", fillcolor="rgba(255,182,18,0.08)",
    ))
    fig_cons.add_hline(y=70, line=dict(color=COLORS["success"], width=1, dash="dot"),
                       annotation_text="Target ≥70%", annotation_position="right")
    apply_theme(fig_cons, height=240)
    fig_cons.update_layout(yaxis=dict(title="%", range=[0, 100]))
    st.plotly_chart(fig_cons, use_container_width=True)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Avg Sleep 28d", f"{last_28['sleep_duration_hrs'].mean():.1f} h")
    with c2:
        st.metric("Deep % of sleep", f"{last_28['sleep_deep_hrs'].mean() / last_28['sleep_duration_hrs'].mean() * 100:.0f}%")
    with c3:
        st.metric("REM % of sleep", f"{last_28['sleep_rem_hrs'].mean() / last_28['sleep_duration_hrs'].mean() * 100:.0f}%")
    with c4:
        st.metric("Consistency 28d", f"{last_28['sleep_consistency_pct'].mean():.0f}%")

# ── Activity ────────────────────────────────────────────────────────────────
with tab_activity:
    st.subheader("Daily Steps & Active Calories")
    df["steps_7d"] = df["steps"].rolling(7, min_periods=1).mean()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df["date"], y=df["steps"],
        name="Steps", marker=dict(color=COLORS["gold"], opacity=0.45),
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["steps_7d"],
        mode="lines", name="Steps 7d",
        line=dict(color=COLORS["gold"], width=3),
    ))
    fig.add_hline(y=8000, line=dict(color=COLORS["success"], width=1, dash="dot"),
                  annotation_text="8k threshold", annotation_position="right")
    apply_theme(fig, height=340)
    fig.update_layout(yaxis=dict(title="Steps"),
                      legend=dict(orientation="h", y=1.1, x=0))
    st.plotly_chart(fig, use_container_width=True)

    fig_cal = go.Figure()
    fig_cal.add_trace(go.Scatter(
        x=df["date"], y=df["active_calories"],
        mode="lines+markers", name="Active kcal",
        line=dict(color=COLORS["chart_series"][3], width=3),
    ))
    fig_cal.add_trace(go.Scatter(
        x=df["date"], y=df["stand_hrs"],
        mode="lines", name="Stand hrs",
        line=dict(color=COLORS["chart_series"][2], width=2),
        yaxis="y2",
    ))
    apply_theme(fig_cal, height=300)
    fig_cal.update_layout(
        yaxis=dict(title="Active kcal"),
        yaxis2=dict(title="Stand hours", overlaying="y", side="right"),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    st.plotly_chart(fig_cal, use_container_width=True)

# ── Raw table ───────────────────────────────────────────────────────────────
with tab_table:
    st.subheader("Wearables — Raw Daily Data")
    show = df.sort_values("date", ascending=False).head(40).copy()
    show["date"] = show["date"].dt.strftime("%Y-%m-%d")
    show_cols = ["date", "resting_hr_bpm", "hrv_sdnn_ms", "vo2_max_ml_kg_min",
                 "sleep_duration_hrs", "sleep_deep_hrs", "sleep_rem_hrs",
                 "sleep_consistency_pct", "respiratory_rate_brpm", "spo2_pct",
                 "active_calories", "steps", "stand_hrs", "skin_temp_delta_f"]
    wear_show = show[show_cols]
    st.dataframe(wear_show, use_container_width=True, hide_index=True,
                 height=full_height(len(wear_show)))
    st.caption(f"{len(wear_show)} row(s)")
