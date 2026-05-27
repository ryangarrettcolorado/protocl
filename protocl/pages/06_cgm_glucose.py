"""CGM Glucose — TIR, AGP curve, meal spikes, daily traces, ketone+GKI."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data
from modules.charts import COLORS, apply_theme, metric_card_html, full_height
from modules.time_range import render_time_range_selector, filter_by_range


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("CGM Glucose")
    st.caption("Time-in-range · ambulatory glucose profile · meal response · ketones")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.cgm_readings.copy()
ketones = data.ketone_readings.copy()

if df.empty:
    st.info("No CGM readings yet.")
    st.stop()

df = df.sort_values("datetime").reset_index(drop=True)
df["date"] = df["datetime"].dt.date
df["hour"] = df["datetime"].dt.hour
df["minute"] = df["datetime"].dt.minute
df["time_of_day"] = df["hour"] + df["minute"] / 60.0

# ────────────────────────────────────────────────────────────────────────────
# Time range selector (replaces the old sidebar day slider)
# ────────────────────────────────────────────────────────────────────────────
tr_start, tr_end, tr_preset = render_time_range_selector("cgm_glucose", default_preset="30d")
win = filter_by_range(df, "datetime", tr_start, tr_end).copy()
if win.empty:
    st.info("No CGM readings in the selected time range.")
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# Core metrics: TIR, mean, CV, GMI
# ────────────────────────────────────────────────────────────────────────────
g = win["glucose_mg_dl"].dropna()
mean_g = g.mean()
sd_g = g.std()
cv_pct = (sd_g / mean_g * 100) if mean_g else 0
gmi = 3.31 + 0.02392 * mean_g  # GMI formula → estimated A1c
tir = ((g >= 70) & (g <= 140)).mean() * 100
tight_tir = ((g >= 70) & (g <= 110)).mean() * 100
above = (g > 140).mean() * 100
below = (g < 70).mean() * 100

kpis = [
    ("TIR (70–140)", f"{tir:.0f}%", "target ≥85%", tir >= 85),
    ("TIGHT TIR (70–110)", f"{tight_tir:.0f}%", "metabolic gold", tight_tir >= 70),
    ("MEAN GLUCOSE", f"{mean_g:.0f} mg/dL", f"GMI ≈ {gmi:.2f}% A1c", mean_g < 100),
    ("CV%", f"{cv_pct:.1f}%", "target <33%", cv_pct < 33),
    ("ABOVE RANGE", f"{above:.1f}%", "spikes >140", above < 5),
    ("BELOW RANGE", f"{below:.1f}%", "<70 mg/dL", below < 2),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_agp, tab_daily, tab_dist, tab_meals, tab_ketones = grouped_sections(
    ["📉 AGP Curve", "📅 Daily Traces", "📊 Distribution", "🍽️ Meal Response", "🟣 Ketones / GKI"]
)

# ── AGP curve ───────────────────────────────────────────────────────────────
with tab_agp:
    st.subheader("Ambulatory Glucose Profile")
    st.caption("Hourly percentile bands across the selected window — the canonical CGM read-out.")

    # Bucket into 30-min slots
    win["tod_bin"] = (win["time_of_day"] * 2).round() / 2  # 0.5h bins
    grouped = win.groupby("tod_bin")["glucose_mg_dl"].agg(
        p5=lambda s: np.percentile(s, 5),
        p25=lambda s: np.percentile(s, 25),
        p50=lambda s: np.percentile(s, 50),
        p75=lambda s: np.percentile(s, 75),
        p95=lambda s: np.percentile(s, 95),
    ).reset_index()

    fig = go.Figure()
    # 5-95 band
    fig.add_trace(go.Scatter(x=grouped["tod_bin"], y=grouped["p95"], mode="lines",
                              line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grouped["tod_bin"], y=grouped["p5"], mode="lines",
                              line=dict(width=0), fill="tonexty",
                              fillcolor="rgba(255,182,18,0.10)", name="5–95%", hoverinfo="skip"))
    # 25-75 band
    fig.add_trace(go.Scatter(x=grouped["tod_bin"], y=grouped["p75"], mode="lines",
                              line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grouped["tod_bin"], y=grouped["p25"], mode="lines",
                              line=dict(width=0), fill="tonexty",
                              fillcolor="rgba(255,182,18,0.25)", name="25–75%", hoverinfo="skip"))
    # Median
    fig.add_trace(go.Scatter(x=grouped["tod_bin"], y=grouped["p50"], mode="lines",
                              line=dict(color=COLORS["gold"], width=3), name="Median"))
    # Range lines
    fig.add_hline(y=140, line=dict(color=COLORS["warning"], width=1, dash="dot"),
                  annotation_text="Upper TIR (140)", annotation_position="right")
    fig.add_hline(y=70, line=dict(color=COLORS["danger"], width=1, dash="dot"),
                  annotation_text="Lower TIR (70)", annotation_position="right")
    fig.add_hline(y=100, line=dict(color=COLORS["text_faint"], width=1, dash="dash"))

    apply_theme(fig, height=440)
    fig.update_layout(
        xaxis=dict(title="Hour of day", tickmode="array",
                   tickvals=list(range(0, 25, 3)),
                   ticktext=[f"{h:02d}:00" for h in range(0, 25, 3)],
                   range=[0, 24]),
        yaxis=dict(title="Glucose (mg/dL)"),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Daily traces ────────────────────────────────────────────────────────────
with tab_daily:
    st.subheader("Daily Glucose Traces")
    st.caption("One line per day. Hover any line to find that day's signature.")

    fig = go.Figure()
    dates_in_win = sorted(win["date"].unique())[-7:]  # last 7 days
    palette = COLORS["chart_series"] * 5
    for i, d in enumerate(dates_in_win):
        day = win[win["date"] == d].sort_values("time_of_day")
        fig.add_trace(go.Scatter(
            x=day["time_of_day"], y=day["glucose_mg_dl"],
            mode="lines",
            name=str(d),
            line=dict(color=palette[i], width=2),
            opacity=0.85,
        ))
    fig.add_hline(y=140, line=dict(color=COLORS["warning"], width=1, dash="dot"))
    fig.add_hline(y=70, line=dict(color=COLORS["danger"], width=1, dash="dot"))
    apply_theme(fig, height=440)
    fig.update_layout(
        xaxis=dict(title="Hour of day", tickmode="array",
                   tickvals=list(range(0, 25, 3)),
                   ticktext=[f"{h:02d}:00" for h in range(0, 25, 3)],
                   range=[0, 24]),
        yaxis=dict(title="Glucose (mg/dL)"),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

# ── Distribution ────────────────────────────────────────────────────────────
with tab_dist:
    st.subheader("Glucose Distribution")
    c1, c2 = st.columns(2)
    with c1:
        fig_hist = go.Figure(go.Histogram(
            x=g, nbinsx=40,
            marker=dict(color=COLORS["gold"], line=dict(color=COLORS["steel_dark"], width=1)),
        ))
        fig_hist.add_vline(x=70, line=dict(color=COLORS["danger"], width=1, dash="dot"))
        fig_hist.add_vline(x=140, line=dict(color=COLORS["warning"], width=1, dash="dot"))
        fig_hist.add_vline(x=mean_g, line=dict(color=COLORS["text_primary"], width=2, dash="dash"),
                            annotation_text=f"Mean {mean_g:.0f}", annotation_position="top")
        apply_theme(fig_hist, height=380)
        fig_hist.update_layout(xaxis=dict(title="Glucose (mg/dL)"), yaxis=dict(title="Readings"))
        st.plotly_chart(fig_hist, use_container_width=True)
    with c2:
        # TIR stacked bar
        ranges = pd.DataFrame({
            "band": ["Very High >180", "High 140-180", "In Range 70-140",
                     "Low 54-69", "Very Low <54"],
            "pct": [
                (g > 180).mean() * 100,
                ((g > 140) & (g <= 180)).mean() * 100,
                ((g >= 70) & (g <= 140)).mean() * 100,
                ((g >= 54) & (g < 70)).mean() * 100,
                (g < 54).mean() * 100,
            ],
            "color": [COLORS["danger"], COLORS["warning"], COLORS["success"],
                      "#FFCDD2", COLORS["danger"]],
        })
        fig_tir = go.Figure()
        for _, row in ranges.iterrows():
            fig_tir.add_trace(go.Bar(
                y=["TIR"], x=[row["pct"]], orientation="h",
                name=f"{row['band']} ({row['pct']:.1f}%)",
                marker=dict(color=row["color"]),
            ))
        fig_tir.update_layout(barmode="stack")
        apply_theme(fig_tir, height=380)
        fig_tir.update_layout(
            xaxis=dict(title="% of time", range=[0, 100]),
            yaxis=dict(showticklabels=False),
            legend=dict(orientation="v", y=0.5, x=1.02),
        )
        st.plotly_chart(fig_tir, use_container_width=True)

# ── Meal response ───────────────────────────────────────────────────────────
with tab_meals:
    st.subheader("Mealtime Response")
    st.caption("Median glucose by hour — identify the windows where post-meal spikes live.")

    by_hour = win.groupby("hour")["glucose_mg_dl"].agg(["mean", "median", "max", "std"]).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=by_hour["hour"], y=by_hour["mean"],
        name="Mean", marker=dict(color=COLORS["gold"]),
        error_y=dict(type="data", array=by_hour["std"],
                     color=COLORS["text_muted"], thickness=1),
    ))
    fig.add_trace(go.Scatter(
        x=by_hour["hour"], y=by_hour["max"],
        name="Max", mode="lines+markers",
        line=dict(color=COLORS["danger"], width=2, dash="dot"),
    ))
    fig.add_hline(y=140, line=dict(color=COLORS["warning"], width=1, dash="dot"))
    apply_theme(fig, height=400)
    fig.update_layout(
        xaxis=dict(title="Hour of day", dtick=2),
        yaxis=dict(title="Glucose (mg/dL)"),
        legend=dict(orientation="h", y=1.1, x=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Identify largest spike hours
    spike_hours = by_hour.sort_values("max", ascending=False).head(3)
    st.markdown("**Highest-spike windows**")
    for _, row in spike_hours.iterrows():
        st.markdown(f"- **{int(row['hour']):02d}:00** — max {row['max']:.0f}, mean {row['mean']:.0f} mg/dL")

# ── Ketones / GKI ───────────────────────────────────────────────────────────
with tab_ketones:
    st.subheader("Ketones + Glucose-Ketone Index")
    if ketones.empty:
        st.info("No ketone readings yet.")
    else:
        ketones = ketones.sort_values("datetime")
        c1, c2 = st.columns(2)
        with c1:
            fig_k = go.Figure()
            fig_k.add_trace(go.Scatter(
                x=ketones["datetime"], y=ketones["blood_ketones_mmol_l"],
                mode="lines+markers", name="Blood Ketones",
                line=dict(color=COLORS["chart_series"][4], width=3),
                marker=dict(size=8),
            ))
            fig_k.add_hline(y=0.5, line=dict(color=COLORS["success"], width=1, dash="dot"),
                             annotation_text="Nutritional ketosis (0.5)", annotation_position="right")
            apply_theme(fig_k, height=320)
            fig_k.update_layout(yaxis=dict(title="mmol/L"))
            st.plotly_chart(fig_k, use_container_width=True)
            st.caption(f"Latest: **{ketones['blood_ketones_mmol_l'].iloc[-1]:.2f} mmol/L**")
        with c2:
            fig_gki = go.Figure()
            fig_gki.add_trace(go.Scatter(
                x=ketones["datetime"], y=ketones["gki"],
                mode="lines+markers", name="GKI",
                line=dict(color=COLORS["gold"], width=3),
                marker=dict(size=8),
            ))
            fig_gki.add_hline(y=9, line=dict(color=COLORS["success"], width=1, dash="dot"),
                               annotation_text="Therapeutic ketosis (≤9)", annotation_position="right")
            apply_theme(fig_gki, height=320)
            fig_gki.update_layout(yaxis=dict(title="GKI (lower = deeper ketosis)"))
            st.plotly_chart(fig_gki, use_container_width=True)
            st.caption(f"Latest GKI: **{ketones['gki'].iloc[-1]:.1f}**")

        ketones_show = ketones.assign(
            datetime=ketones["datetime"].dt.strftime("%Y-%m-%d %H:%M")
        )[["datetime", "blood_ketones_mmol_l", "blood_glucose_mg_dl", "gki", "source", "notes"]]\
            .sort_values("datetime", ascending=False)
        st.dataframe(ketones_show, use_container_width=True, hide_index=True,
                     height=full_height(len(ketones_show)))
        st.caption(f"{len(ketones_show)} row(s)")
