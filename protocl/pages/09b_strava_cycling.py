"""Strava Cycling — dedicated road/MTB ride analysis from Strava-sourced data."""
from __future__ import annotations

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
    st.title("🚴 Strava Cycling")
    st.caption("Strava-sourced rides — volume, elevation, power, intensity")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.training.copy()

if df.empty:
    st.info("No training data yet.")
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# Filter to cycling activities sourced from Strava
# ────────────────────────────────────────────────────────────────────────────
CYCLING_TYPES = ["mtb", "ride", "ebike"]
df["source_str"] = df.get("source", "").fillna("").astype(str)
df = df[df["activity_type"].isin(CYCLING_TYPES)].copy()
df = df[df["source_str"].str.contains("strava", case=False, na=False)]

if df.empty:
    st.info("No Strava cycling activities yet — connect Strava in Integrations.")
    st.stop()

df = df.sort_values("date").reset_index(drop=True)

# Page time range
tr_start, tr_end, tr_preset = render_time_range_selector(
    "strava_cycling", default_preset="1yr"
)
df = filter_by_range(df, "date", tr_start, tr_end).sort_values("date").reset_index(drop=True)

if df.empty:
    st.info("No cycling activities in the selected time range.")
    st.stop()

df["mph"] = df["distance_miles"] / (df["duration_min"] / 60).replace(0, pd.NA)
df["ft_per_mi"] = df["elevation_ft"] / df["distance_miles"].replace(0, pd.NA)
df["week"] = df["date"].dt.to_period("W").dt.start_time
df["month"] = df["date"].dt.to_period("M").dt.start_time

TYPE_LABELS = {"mtb": "MTB", "ride": "Road", "ebike": "E-bike"}
TYPE_COLORS = {
    "mtb":   COLORS["gold"],
    "ride":  COLORS["chart_series"][0],
    "ebike": COLORS["chart_series"][2],
}

# ────────────────────────────────────────────────────────────────────────────
# KPI row
# ────────────────────────────────────────────────────────────────────────────
total_dist = df["distance_miles"].sum()
total_elev = df["elevation_ft"].sum()
avg_speed = df["mph"].mean()
avg_power = df["avg_power_watts"].mean() if df["avg_power_watts"].notna().any() else None
longest = df["distance_miles"].max()
ride_count = len(df)

kpis = [
    ("RIDES", f"{ride_count}", "in range", None),
    ("TOTAL DIST", f"{total_dist:,.0f} mi", "all bikes", None),
    ("TOTAL CLIMB", f"{total_elev:,.0f} ft",
     f"{total_elev/5280:.1f} mi vertical", None),
    ("AVG SPEED", f"{avg_speed:.1f} mph" if pd.notna(avg_speed) else "—",
     "per ride", None),
    ("AVG POWER",
     f"{avg_power:.0f} W" if avg_power is not None else "—",
     "rides w/ power data", None),
    ("LONGEST RIDE",
     f"{longest:.1f} mi" if pd.notna(longest) else "—",
     "single day", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_volume, tab_elev, tab_intensity, tab_rides = grouped_sections(
    ["📈 Weekly Volume", "⛰️ Elevation Trend", "🔥 Zone Intensity", "📋 Ride Log"]
)

# ── Weekly volume ───────────────────────────────────────────────────────────
with tab_volume:
    st.subheader("Weekly Cycling Volume")
    weekly = df.groupby(["week", "activity_type"]).agg(
        miles=("distance_miles", "sum"),
        hours=("duration_min", lambda s: s.sum() / 60),
    ).reset_index()
    fig = go.Figure()
    for atype in ["mtb", "ride", "ebike"]:
        sub = weekly[weekly["activity_type"] == atype]
        if sub.empty:
            continue
        fig.add_trace(go.Bar(
            x=sub["week"], y=sub["miles"],
            name=TYPE_LABELS[atype],
            marker=dict(color=TYPE_COLORS[atype]),
        ))
    # 7-day rolling mean line (across all cycling types)
    daily = df.groupby(df["date"].dt.date)["distance_miles"].sum()
    daily.index = pd.to_datetime(daily.index)
    daily_full = daily.reindex(
        pd.date_range(daily.index.min(), daily.index.max()), fill_value=0
    )
    rolling_7 = daily_full.rolling(7, min_periods=2).mean() * 7  # weekly equivalent
    fig.add_trace(go.Scatter(
        x=rolling_7.index, y=rolling_7.values,
        mode="lines", name="7d×7 trend",
        line=dict(color=COLORS["text_primary"], width=2, dash="dash"),
        opacity=0.7,
    ))
    apply_theme(fig, height=380)
    fig.update_layout(
        barmode="stack",
        yaxis=dict(title="Miles"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Monthly hours
    st.subheader("Monthly Hours")
    monthly = df.groupby("month").agg(
        hours=("duration_min", lambda s: s.sum() / 60),
        rides=("date", "count"),
    ).reset_index()
    fig_h = go.Figure()
    fig_h.add_trace(go.Bar(
        x=monthly["month"], y=monthly["hours"],
        marker=dict(color=COLORS["gold"]),
        text=monthly["rides"].astype(str) + " rides",
        textposition="outside",
    ))
    apply_theme(fig_h, height=320)
    fig_h.update_layout(yaxis=dict(title="Hours"), showlegend=False)
    st.plotly_chart(fig_h, use_container_width=True)

# ── Elevation trend ─────────────────────────────────────────────────────────
with tab_elev:
    st.subheader("Elevation Gain Over Time")
    st.caption("Bars = monthly climbing total · line = 3-month rolling average")

    elev_monthly = df.groupby("month")["elevation_ft"].sum().reset_index()
    elev_monthly["roll_3"] = elev_monthly["elevation_ft"].rolling(3, min_periods=1).mean()

    fig_e = go.Figure()
    fig_e.add_trace(go.Bar(
        x=elev_monthly["month"], y=elev_monthly["elevation_ft"],
        marker=dict(color=COLORS["chart_series"][2], opacity=0.55),
        name="Monthly climbing",
    ))
    fig_e.add_trace(go.Scatter(
        x=elev_monthly["month"], y=elev_monthly["roll_3"],
        mode="lines+markers", name="3-month avg",
        line=dict(color=COLORS["gold"], width=3),
    ))
    apply_theme(fig_e, height=380)
    fig_e.update_layout(
        yaxis=dict(title="Feet climbed"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig_e, use_container_width=True)

    # Per-ride climb rate (ft/mi) — terrain difficulty fingerprint
    st.subheader("Per-Ride Climb Rate")
    st.caption("Feet of climbing per mile. <100 = flat · 100-150 rolling · 150-250 hilly · >250 punchy.")
    cyc_elev = df[df["elevation_ft"].notna() & (df["distance_miles"] >= 1)].copy()
    if not cyc_elev.empty:
        fig_climb = go.Figure()
        for atype in ["mtb", "ride", "ebike"]:
            sub = cyc_elev[cyc_elev["activity_type"] == atype]
            if sub.empty:
                continue
            fig_climb.add_trace(go.Scatter(
                x=sub["date"], y=sub["ft_per_mi"],
                mode="markers", name=TYPE_LABELS[atype],
                marker=dict(
                    color=TYPE_COLORS[atype],
                    size=(sub["distance_miles"] * 1.4).clip(6, 26),
                    line=dict(color="#0E0E10", width=1),
                    opacity=0.85,
                ),
                customdata=sub[["distance_miles", "elevation_ft"]].values,
                hovertemplate=(
                    "<b>%{x|%b %d, %Y}</b><br>"
                    "%{customdata[0]:.1f} mi · %{customdata[1]:.0f} ft<br>"
                    "<b>%{y:.0f} ft/mi</b><extra></extra>"
                ),
            ))
        apply_theme(fig_climb, height=360)
        fig_climb.update_layout(
            yaxis=dict(title="Feet per mile"),
            legend=dict(orientation="h", y=1.1, x=0),
        )
        st.plotly_chart(fig_climb, use_container_width=True)

# ── Zone intensity ──────────────────────────────────────────────────────────
with tab_intensity:
    st.subheader("HR Zone Distribution")

    Z1 = "Z1 — Active Recovery (<55% HR max)"
    Z2 = "Z2 — Aerobic Base (55–70% HR max)"
    Z3 = "Z3 — Aerobic Tempo (70–80% HR max)"
    Z4 = "Z4 — Threshold (80–90% HR max)"
    Z5 = "Z5 — VO₂ Max Effort (90–100% HR max)"

    def zone_of(hr):
        if pd.isna(hr): return "Unknown"
        if hr < 122: return Z1
        if hr < 145: return Z2
        if hr < 160: return Z3
        if hr < 172: return Z4
        return Z5

    z = df.copy()
    z["zone"] = z["avg_hr_bpm"].apply(zone_of)
    zone_mins = z.groupby("zone")["duration_min"].sum().reset_index()
    zone_order = [Z1, Z2, Z3, Z4, Z5, "Unknown"]
    zone_mins["zone"] = pd.Categorical(zone_mins["zone"], categories=zone_order, ordered=True)
    zone_mins = zone_mins.sort_values("zone").dropna(subset=["zone"])
    zone_colors = {
        Z1: "#80DEEA",
        Z2: COLORS["success"],
        Z3: COLORS["gold"],
        Z4: COLORS["warning"],
        Z5: COLORS["danger"],
        "Unknown": COLORS["text_faint"],
    }
    total_min = zone_mins["duration_min"].sum()

    c1, c2 = st.columns([3, 2])
    with c1:
        fig_z = go.Figure(go.Bar(
            x=zone_mins["zone"], y=zone_mins["duration_min"],
            marker=dict(color=[zone_colors.get(z, "#888") for z in zone_mins["zone"]]),
            text=[f"{m:.0f}m ({m/total_min*100:.0f}%)" if total_min else "—"
                  for m in zone_mins["duration_min"]],
            textposition="outside",
        ))
        apply_theme(fig_z, height=360)
        fig_z.update_layout(yaxis=dict(title="Minutes"), showlegend=False)
        st.plotly_chart(fig_z, use_container_width=True)
    with c2:
        st.metric("Total cycling time (zoned)", f"{total_min/60:.1f} h")
        z2_min = zone_mins[zone_mins["zone"] == Z2]["duration_min"].sum()
        st.metric("Z2 aerobic share",
                  f"{z2_min/total_min*100:.0f}%" if total_min else "—",
                  help="Polarized training models target ~75-80% Z1–Z2.")
        hi_min = zone_mins[zone_mins["zone"].isin([Z3, Z4, Z5])]["duration_min"].sum()
        st.metric("High-intensity share (Z3+)",
                  f"{hi_min/total_min*100:.0f}%" if total_min else "—")

    st.caption(
        "**Zone system** — Z1 Active Recovery (<55% HR max), Z2 Aerobic Base (55–70%), "
        "Z3 Aerobic Tempo (70–80%), Z4 Threshold (80–90%), Z5 VO₂ Max Effort (90–100%)."
    )

# ── Ride log ────────────────────────────────────────────────────────────────
with tab_rides:
    st.subheader("Ride Log")
    show = df.sort_values("date", ascending=False).copy()
    show["Date"] = show["date"].dt.strftime("%Y-%m-%d")
    show["Type"] = show["activity_type"].map(TYPE_LABELS).fillna(show["activity_type"])
    show["Distance"] = show["distance_miles"].round(1)
    show["Climbing"] = show["elevation_ft"].apply(
        lambda x: f"{int(x):,} ft" if pd.notna(x) else "—"
    )
    show["Duration"] = show["duration_min"].apply(
        lambda x: f"{int(x // 60)}h {int(x % 60):02d}m" if pd.notna(x) else "—"
    )
    show["Avg Speed"] = show["mph"].apply(
        lambda x: f"{x:.1f} mph" if pd.notna(x) else "—"
    )
    show["Avg HR"] = show["avg_hr_bpm"].apply(
        lambda x: f"{x:.0f}" if pd.notna(x) else "—"
    )
    show["Avg Power"] = show["avg_power_watts"].apply(
        lambda x: f"{x:.0f} W" if pd.notna(x) else "—"
    )
    show["TSS"] = show["tss"].apply(lambda x: f"{int(x)}" if pd.notna(x) else "—")

    cols_show = ["Date", "Type", "Distance", "Climbing", "Duration",
                 "Avg Speed", "Avg HR", "Avg Power", "TSS", "notes"]
    rides_show = show[cols_show].rename(columns={"notes": "Notes"})
    st.dataframe(rides_show, use_container_width=True, hide_index=True,
                 height=full_height(len(rides_show)))
    st.caption(f"{len(rides_show)} ride(s)")
