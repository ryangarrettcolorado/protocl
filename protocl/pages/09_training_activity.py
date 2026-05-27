"""Training Activity — volume, TSS, intensity, calendar heatmap, recent sessions."""
from __future__ import annotations

from datetime import timedelta

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
    st.title("Training Activity")
    st.caption("Volume, intensity distribution, TSS load, and recent sessions")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.training.copy()

if df.empty:
    st.info("No training sessions logged yet.")
    st.stop()

df = df.sort_values("date").reset_index(drop=True)
df["week"] = df["date"].dt.to_period("W").dt.start_time

TODAY = pd.Timestamp("2026-05-25")

# Page time range — filters every chart and table below. 7D / 28D KPI cards
# remain anchored to absolute windows because those are part of the headline
# definitions and shouldn't shift with the range selector.
tr_start, tr_end, tr_preset = render_time_range_selector("training_activity", default_preset="1yr")
df = filter_by_range(df, "date", tr_start, tr_end).sort_values("date").reset_index(drop=True)

if df.empty:
    st.info("No training sessions in the selected time range.")
    st.stop()
df["week"] = df["date"].dt.to_period("W").dt.start_time
last_7 = df[df["date"] >= TODAY - pd.Timedelta(days=7)]
last_28 = df[df["date"] >= TODAY - pd.Timedelta(days=28)]
prev_28 = df[(df["date"] >= TODAY - pd.Timedelta(days=56)) & (df["date"] < TODAY - pd.Timedelta(days=28))]

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
hrs_7 = last_7["duration_min"].sum() / 60
miles_7 = last_7["distance_miles"].sum()
tss_7 = last_7["tss"].sum()
sessions_7 = len(last_7)
hrs_28 = last_28["duration_min"].sum() / 60
hrs_28_prev = prev_28["duration_min"].sum() / 60
delta_hrs = hrs_28 - hrs_28_prev
elev_28 = last_28["elevation_ft"].sum()

kpis = [
    ("7D HOURS", f"{hrs_7:.1f}h", f"{sessions_7} sessions", hrs_7 >= 5),
    ("7D MILES", f"{miles_7:.0f} mi", f"{miles_7/7:.1f} mi/day", None),
    ("7D TSS", f"{int(tss_7)}", "training stress", tss_7 >= 300),
    ("28D HOURS", f"{hrs_28:.1f}h", f"{delta_hrs:+.1f}h vs prior 28d", delta_hrs >= 0),
    ("28D ELEVATION", f"{int(elev_28):,} ft", "climbing volume", None),
    ("AVG SESSION", f"{last_28['duration_min'].mean():.0f} min", "last 28d", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_load, tab_intensity, tab_cycling, tab_calendar, tab_sessions = grouped_sections(
    ["📈 Load & Volume", "🔥 Intensity", "🚵 Cycling & MTB", "🗓️ Calendar", "📋 Sessions"]
)

# ── Load & Volume ───────────────────────────────────────────────────────────
with tab_load:
    st.subheader("Weekly Volume & TSS")

    weekly = df.groupby("week").agg(
        hours=("duration_min", lambda s: s.sum() / 60),
        miles=("distance_miles", "sum"),
        tss=("tss", "sum"),
        elev=("elevation_ft", "sum"),
        sessions=("date", "count"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=weekly["week"], y=weekly["hours"],
        name="Hours", marker=dict(color=COLORS["gold"]),
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=weekly["week"], y=weekly["tss"],
        name="TSS", mode="lines+markers",
        line=dict(color=COLORS["chart_series"][1], width=3),
        marker=dict(size=8),
        yaxis="y2",
    ))
    apply_theme(fig, height=380)
    fig.update_layout(
        yaxis=dict(title="Hours", gridcolor="#2A2A2A"),
        yaxis2=dict(title="TSS", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Acute:Chronic ratio (7d hours / 28d hours per day)
    st.subheader("Acute : Chronic Training Load")
    st.caption("Ratio of 7-day load to 28-day load. Sweet spot ≈ 0.8–1.3. >1.5 = injury risk.")
    df_daily = df.groupby(df["date"].dt.date)["tss"].sum().reset_index()
    df_daily["date"] = pd.to_datetime(df_daily["date"])
    all_days = pd.date_range(df_daily["date"].min(), df_daily["date"].max())
    df_daily = df_daily.set_index("date").reindex(all_days, fill_value=0).rename_axis("date").reset_index()
    df_daily["acute"] = df_daily["tss"].rolling(7).mean()
    df_daily["chronic"] = df_daily["tss"].rolling(28).mean()
    df_daily["acwr"] = df_daily["acute"] / df_daily["chronic"]
    df_daily = df_daily.dropna()

    fig_acwr = go.Figure()
    fig_acwr.add_trace(go.Scatter(
        x=df_daily["date"], y=df_daily["acwr"],
        mode="lines", name="ACWR",
        line=dict(color=COLORS["gold"], width=3),
    ))
    fig_acwr.add_hrect(y0=0.8, y1=1.3, fillcolor="rgba(76,175,80,0.10)",
                        line=dict(width=0), annotation_text="Optimal", annotation_position="top left")
    fig_acwr.add_hline(y=1.5, line=dict(color=COLORS["danger"], width=1, dash="dot"),
                        annotation_text="Injury risk", annotation_position="right")
    apply_theme(fig_acwr, height=300)
    fig_acwr.update_layout(yaxis=dict(title="ACWR"))
    st.plotly_chart(fig_acwr, use_container_width=True)

# ── Intensity ───────────────────────────────────────────────────────────────
with tab_intensity:
    st.subheader("Intensity Distribution (Last 28 Days)")
    st.caption("Time in each HR zone — rough breakdown from average HR per session.")

    # Approximate HR zones based on avg_hr (assume max HR ~178, lthr ~155)
    # Z1: <122, Z2: 122-145, Z3: 146-160, Z4: 161-172, Z5: >172
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

    last_28_z = last_28.copy()
    last_28_z["zone"] = last_28_z["avg_hr_bpm"].apply(zone_of)
    zone_mins = last_28_z.groupby("zone")["duration_min"].sum().reset_index()
    zone_order = [Z1, Z2, Z3, Z4, Z5, "Unknown"]
    zone_mins["zone"] = pd.Categorical(zone_mins["zone"], categories=zone_order, ordered=True)
    zone_mins = zone_mins.sort_values("zone")
    zone_colors = {
        Z1: "#80DEEA",
        Z2: COLORS["success"],
        Z3: COLORS["gold"],
        Z4: COLORS["warning"],
        Z5: COLORS["danger"],
        "Unknown": COLORS["text_faint"],
    }

    c1, c2 = st.columns([3, 2])
    with c1:
        fig_z = go.Figure(go.Bar(
            x=zone_mins["zone"], y=zone_mins["duration_min"],
            marker=dict(color=[zone_colors[z] for z in zone_mins["zone"]]),
            text=[f"{m:.0f}m" for m in zone_mins["duration_min"]],
            textposition="outside",
        ))
        apply_theme(fig_z, height=360)
        fig_z.update_layout(yaxis=dict(title="Minutes"), showlegend=False)
        st.plotly_chart(fig_z, use_container_width=True)
    with c2:
        fig_pie = go.Figure(go.Pie(
            labels=zone_mins["zone"], values=zone_mins["duration_min"],
            hole=0.55,
            marker=dict(colors=[zone_colors[z] for z in zone_mins["zone"]]),
            textinfo="percent",
        ))
        apply_theme(fig_pie, height=360)
        fig_pie.update_layout(showlegend=True, legend=dict(orientation="v", y=0.5, x=1.05))
        st.plotly_chart(fig_pie, use_container_width=True)

    st.caption(
        "**Zone system** — Z1 Active Recovery (<55% HR max), Z2 Aerobic Base (55–70%), "
        "Z3 Aerobic Tempo (70–80%), Z4 Threshold (80–90%), Z5 VO₂ Max Effort (90–100%). "
        "Polarized training targets ~75–80% of weekly time in Z1–Z2 and the remainder in Z4–Z5."
    )

    # Power / cadence stats
    st.subheader("Power & Cadence Trends")
    rides = df[df["activity_type"] == "ride"].copy()
    if not rides.empty and rides["avg_power_watts"].notna().any():
        rides["week"] = rides["date"].dt.to_period("W").dt.start_time
        wk_pwr = rides.groupby("week").agg(
            avg_power=("avg_power_watts", "mean"),
            avg_cadence=("avg_cadence_rpm", "mean"),
        ).reset_index()
        fig_pwr = go.Figure()
        fig_pwr.add_trace(go.Scatter(x=wk_pwr["week"], y=wk_pwr["avg_power"],
                                       name="Avg Power (W)", mode="lines+markers",
                                       line=dict(color=COLORS["gold"], width=3)))
        fig_pwr.add_trace(go.Scatter(x=wk_pwr["week"], y=wk_pwr["avg_cadence"],
                                       name="Avg Cadence (rpm)", mode="lines+markers",
                                       line=dict(color=COLORS["chart_series"][1], width=3),
                                       yaxis="y2"))
        apply_theme(fig_pwr, height=320)
        fig_pwr.update_layout(
            yaxis=dict(title="Watts"),
            yaxis2=dict(title="Cadence", overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.1, x=0),
        )
        st.plotly_chart(fig_pwr, use_container_width=True)

# ── Cycling & MTB ───────────────────────────────────────────────────────────
with tab_cycling:
    CYCLING_TYPES = ["mtb", "ride", "ebike"]
    cyc = df[df["activity_type"].isin(CYCLING_TYPES)].copy()
    cyc = cyc.sort_values("date")

    if cyc.empty:
        st.info("No cycling activities logged yet.")
    else:
        cyc["ft_per_mi"] = cyc["elevation_ft"] / cyc["distance_miles"]
        cyc["mph"] = cyc["distance_miles"] / (cyc["duration_min"] / 60)
        cyc["month"] = cyc["date"].dt.to_period("M").dt.start_time

        # 12-month headline KPIs
        win_start = TODAY - pd.Timedelta(days=365)
        c12 = cyc[cyc["date"] >= win_start]
        mtb_12 = c12[c12["activity_type"] == "mtb"]
        road_12 = c12[c12["activity_type"] == "ride"]

        kpi_cards = [
            ("12M RIDES", f"{len(c12)}", f"{len(mtb_12)} MTB · {len(road_12)} road", None),
            ("12M MILES", f"{c12['distance_miles'].sum():.0f}", "all bikes", None),
            ("12M CLIMBING", f"{c12['elevation_ft'].sum():,.0f} ft",
             f"{c12['elevation_ft'].sum()/5280:.1f} mi of vertical", None),
            ("AVG MTB RIDE",
             f"{mtb_12['distance_miles'].mean():.1f} mi" if len(mtb_12) else "—",
             f"{mtb_12['elevation_ft'].mean():.0f} ft · {mtb_12['ft_per_mi'].mean():.0f} ft/mi"
             if len(mtb_12) else "", None),
            ("AVG MTB SPEED",
             f"{mtb_12['mph'].mean():.1f} mph" if len(mtb_12) else "—",
             "climbing-heavy terrain", None),
            ("AVG ROAD POWER",
             f"{road_12['avg_power_watts'].mean():.0f} W" if road_12['avg_power_watts'].notna().any() else "—",
             f"{road_12['avg_power_watts'].notna().sum()} rides w/ power", None),
        ]
        cols = st.columns(6)
        for col, (label, value, delta, pos) in zip(cols, kpi_cards):
            with col:
                st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

        st.markdown("")

        # Monthly volume — stacked bar (miles) + climb line
        st.subheader("Monthly Volume")
        st.caption("Bars = miles by ride type · Line = total feet climbed")

        m_pivot = cyc.pivot_table(
            index="month", columns="activity_type", values="distance_miles",
            aggfunc="sum", fill_value=0,
        )
        elev_by_month = cyc.groupby("month")["elevation_ft"].sum()

        type_colors = {
            "mtb":   COLORS["gold"],
            "ride":  COLORS["chart_series"][1],
            "ebike": COLORS["chart_series"][2],
        }
        type_labels = {"mtb": "MTB", "ride": "Road", "ebike": "E-bike"}

        fig_vol = go.Figure()
        for atype in ["mtb", "ride", "ebike"]:
            if atype not in m_pivot.columns:
                continue
            fig_vol.add_trace(go.Bar(
                x=m_pivot.index, y=m_pivot[atype],
                name=type_labels[atype],
                marker=dict(color=type_colors[atype]),
            ))
        fig_vol.add_trace(go.Scatter(
            x=elev_by_month.index, y=elev_by_month.values,
            name="Climbing (ft)",
            mode="lines+markers",
            line=dict(color=COLORS["warning"], width=3),
            marker=dict(size=8),
            yaxis="y2",
        ))
        apply_theme(fig_vol, height=380)
        fig_vol.update_layout(
            barmode="stack",
            yaxis=dict(title="Miles", gridcolor="#2A2A2A"),
            yaxis2=dict(title="Elevation (ft)", overlaying="y", side="right",
                         gridcolor="rgba(0,0,0,0)"),
            legend=dict(orientation="h", y=1.1, x=0),
            hovermode="x unified",
        )
        st.plotly_chart(fig_vol, use_container_width=True)

        # Climb rate per ride (terrain-difficulty fingerprint)
        st.subheader("Climb Rate by Ride")
        st.caption(
            "Feet of climbing per mile. 100–150 ft/mi = rolling · 150–250 = hilly · >250 = punchy MTB. "
            "Bubble size = ride distance."
        )
        cyc_elev = cyc[cyc["elevation_ft"].notna() & (cyc["distance_miles"] >= 1)].copy()
        if not cyc_elev.empty:
            fig_climb = go.Figure()
            for atype in ["mtb", "ride", "ebike"]:
                sub = cyc_elev[cyc_elev["activity_type"] == atype]
                if sub.empty:
                    continue
                fig_climb.add_trace(go.Scatter(
                    x=sub["date"], y=sub["ft_per_mi"],
                    mode="markers",
                    name=type_labels[atype],
                    marker=dict(
                        color=type_colors[atype],
                        size=(sub["distance_miles"] * 1.6).clip(6, 28),
                        line=dict(color="#0E0E10", width=1),
                        opacity=0.85,
                    ),
                    customdata=sub[["distance_miles", "elevation_ft", "duration_min"]].values,
                    hovertemplate=(
                        "<b>%{x|%b %d, %Y}</b><br>"
                        "%{customdata[0]:.1f} mi · %{customdata[1]:.0f} ft · %{customdata[2]:.0f} min<br>"
                        "<b>%{y:.0f} ft/mi</b><extra></extra>"
                    ),
                ))
            fig_climb.add_hrect(y0=100, y1=150, fillcolor="rgba(63,191,127,0.06)",
                                 line=dict(width=0))
            fig_climb.add_hrect(y0=150, y1=250, fillcolor="rgba(255,182,18,0.06)",
                                 line=dict(width=0))
            fig_climb.add_hrect(y0=250, y1=600, fillcolor="rgba(255,90,90,0.06)",
                                 line=dict(width=0))
            apply_theme(fig_climb, height=380)
            fig_climb.update_layout(
                yaxis=dict(title="Feet per mile",
                            range=[0, max(cyc_elev["ft_per_mi"].max() * 1.1, 300)]),
                legend=dict(orientation="h", y=1.1, x=0),
            )
            st.plotly_chart(fig_climb, use_container_width=True)
        else:
            st.info("No rides with elevation data yet.")

        # Power vs Speed scatter
        st.subheader("Power vs Speed")
        st.caption("Each dot = one ride with power data. Up-and-right = stronger output. Bubble size = ride distance.")
        power_rides = cyc[cyc["avg_power_watts"].notna() & cyc["mph"].notna()].copy()
        if len(power_rides) >= 2:
            fig_pwr2 = go.Figure()
            for atype in ["mtb", "ride", "ebike"]:
                sub = power_rides[power_rides["activity_type"] == atype]
                if sub.empty:
                    continue
                fig_pwr2.add_trace(go.Scatter(
                    x=sub["avg_power_watts"], y=sub["mph"],
                    mode="markers",
                    name=type_labels[atype],
                    marker=dict(
                        color=type_colors[atype],
                        size=(sub["distance_miles"] * 1.6).clip(8, 28),
                        line=dict(color="#0E0E10", width=1),
                        opacity=0.85,
                    ),
                    customdata=sub[["date", "distance_miles", "ft_per_mi"]].values,
                    hovertemplate=(
                        "<b>%{customdata[0]|%b %d, %Y}</b><br>"
                        "Power: %{x:.0f} W · Speed: %{y:.1f} mph<br>"
                        "%{customdata[1]:.1f} mi · %{customdata[2]:.0f} ft/mi<extra></extra>"
                    ),
                ))
            apply_theme(fig_pwr2, height=340)
            fig_pwr2.update_layout(
                xaxis=dict(title="Avg Power (W)"),
                yaxis=dict(title="Avg Speed (mph)"),
                legend=dict(orientation="h", y=1.1, x=0),
            )
            st.plotly_chart(fig_pwr2, use_container_width=True)
        else:
            st.info(f"Need 2+ rides with power data. Currently {len(power_rides)} ride(s).")

        # HR zone time-in-zone for cycling (last 12mo)
        cyc_hr = c12[c12["avg_hr_bpm"].notna() & c12["duration_min"].notna()].copy()
        if len(cyc_hr) >= 3:
            st.subheader("HR Zone Distribution — Cycling Only")
            st.caption(
                "Time in each HR zone across cycling rides (last 12mo). "
                "Hour-bucket HR averages, so this approximates the dominant zone per ride."
            )

            def cycling_zone(hr):
                if pd.isna(hr): return "Unknown"
                if hr < 122: return Z1
                if hr < 145: return Z2
                if hr < 160: return Z3
                if hr < 172: return Z4
                return Z5

            cyc_hr["zone"] = cyc_hr["avg_hr_bpm"].apply(cycling_zone)
            zone_mins_c = cyc_hr.groupby("zone")["duration_min"].sum().reset_index()
            zone_order_c = [Z1, Z2, Z3, Z4, Z5]
            zone_mins_c["zone"] = pd.Categorical(zone_mins_c["zone"], categories=zone_order_c, ordered=True)
            zone_mins_c = zone_mins_c.sort_values("zone").dropna(subset=["zone"])
            zone_colors_c = {
                Z1: "#80DEEA",
                Z2: COLORS["success"],
                Z3: COLORS["gold"],
                Z4: COLORS["warning"],
                Z5: COLORS["danger"],
            }
            total_min = zone_mins_c["duration_min"].sum()
            zc1, zc2 = st.columns([3, 2])
            with zc1:
                fig_zc = go.Figure(go.Bar(
                    x=zone_mins_c["zone"], y=zone_mins_c["duration_min"],
                    marker=dict(color=[zone_colors_c.get(z, "#888") for z in zone_mins_c["zone"]]),
                    text=[f"{m:.0f}m ({m/total_min*100:.0f}%)" for m in zone_mins_c["duration_min"]],
                    textposition="outside",
                ))
                apply_theme(fig_zc, height=320)
                fig_zc.update_layout(yaxis=dict(title="Minutes"), showlegend=False)
                st.plotly_chart(fig_zc, use_container_width=True)
            with zc2:
                st.metric("Total cycling time (zones known)", f"{total_min/60:.1f} h")
                z2_min = zone_mins_c[zone_mins_c["zone"] == Z2]["duration_min"].sum()
                z2_pct = z2_min / total_min * 100 if total_min else 0
                st.metric("Z2 aerobic share", f"{z2_pct:.0f}%",
                           help="Polarized training models target ~75-80% Z1-Z2.")
                hi_min = zone_mins_c[zone_mins_c["zone"].isin([Z3, Z4, Z5])]["duration_min"].sum()
                st.metric("High-intensity share (Z3+)", f"{hi_min/total_min*100:.0f}%" if total_min else "—")

            # Aerobic efficiency trend: mph per heartbeat
            st.subheader("Aerobic Efficiency Trend")
            st.caption(
                "Speed-per-heartbeat (mph ÷ avg HR) over time — a fitness proxy. "
                "Rising line = same HR producing more speed. Best on similar terrain."
            )
            eff = cyc_hr.copy()
            eff["efficiency"] = eff["mph"] / eff["avg_hr_bpm"] * 100  # x100 for readable units
            eff = eff.sort_values("date")
            fig_eff = go.Figure()
            for atype in ["mtb", "ride"]:
                sub = eff[eff["activity_type"] == atype]
                if sub.empty:
                    continue
                fig_eff.add_trace(go.Scatter(
                    x=sub["date"], y=sub["efficiency"],
                    mode="markers+lines",
                    name=type_labels.get(atype, atype),
                    line=dict(color=type_colors[atype], width=2),
                    marker=dict(
                        size=(sub["distance_miles"] * 1.4).clip(8, 22),
                        color=type_colors[atype],
                        line=dict(color="#0E0E10", width=1),
                    ),
                    customdata=sub[["distance_miles", "avg_hr_bpm", "mph", "ft_per_mi"]].values,
                    hovertemplate=(
                        "<b>%{x|%b %d, %Y}</b><br>"
                        "Speed/HR ×100: %{y:.2f}<br>"
                        "%{customdata[2]:.1f} mph @ %{customdata[1]:.0f} bpm<br>"
                        "%{customdata[0]:.1f} mi · %{customdata[3]:.0f} ft/mi<extra></extra>"
                    ),
                ))
            apply_theme(fig_eff, height=320)
            fig_eff.update_layout(
                yaxis=dict(title="Speed / HR × 100"),
                legend=dict(orientation="h", y=1.1, x=0),
            )
            st.plotly_chart(fig_eff, use_container_width=True)

        # Biggest rides leaderboard
        st.subheader("Biggest Rides")
        st.caption("Sorted by elevation gain — your biggest days on the bike.")
        big = cyc[cyc["elevation_ft"].notna()].nlargest(8, "elevation_ft").copy()
        big["Date"] = big["date"].dt.strftime("%b %d, %Y")
        big["Type"] = big["activity_type"].map(type_labels)
        big["Distance"] = big["distance_miles"].round(1).astype(str) + " mi"
        big["Climbing"] = big["elevation_ft"].apply(lambda x: f"{int(x):,} ft")
        big["Duration"] = big["duration_min"].apply(
            lambda x: f"{int(x // 60)}h {int(x % 60):02d}m" if pd.notna(x) else "—"
        )
        big["Climb Rate"] = big["ft_per_mi"].apply(
            lambda x: f"{int(x)} ft/mi" if pd.notna(x) else "—"
        )
        big["Avg Power"] = big["avg_power_watts"].apply(
            lambda x: f"{x:.0f} W" if pd.notna(x) else "—"
        )
        big["Effort"] = big["tss"].apply(lambda x: f"{int(x)}" if pd.notna(x) else "—")
        big["Title"] = big["notes"].fillna("").str.split("·").str[0].str.strip().str.slice(0, 32)
        big_show = big[["Date", "Type", "Title", "Distance", "Climbing", "Climb Rate",
                         "Duration", "Avg Power", "Effort"]]
        st.dataframe(
            big_show,
            use_container_width=True, hide_index=True,
            height=full_height(len(big_show)),
        )
        st.caption(f"{len(big_show)} row(s)")

        # Ride type mix
        st.subheader("Ride Type Mix (Last 12 Months)")
        mix_12 = c12.groupby("activity_type").agg(
            Rides=("date", "count"),
            Miles=("distance_miles", "sum"),
            Climbing=("elevation_ft", "sum"),
            Hours=("duration_min", lambda s: s.sum() / 60),
        ).reset_index()
        mix_12["activity_type"] = mix_12["activity_type"].map(type_labels)
        mix_12["Miles"] = mix_12["Miles"].round(1)
        mix_12["Climbing"] = mix_12["Climbing"].fillna(0).round(0).astype(int)
        mix_12["Hours"] = mix_12["Hours"].round(1)
        mix_12 = mix_12.rename(columns={"activity_type": "Type"}).sort_values("Miles", ascending=False)
        st.dataframe(mix_12, use_container_width=True, hide_index=True,
                     height=full_height(len(mix_12)))


# ── Calendar ────────────────────────────────────────────────────────────────
with tab_calendar:
    st.subheader("Training Calendar (Last 16 Weeks)")
    st.caption("Each square = one day. Color intensity = TSS for that day.")

    end = TODAY
    start = end - pd.Timedelta(weeks=16)
    daily_tss = df.groupby(df["date"].dt.date)["tss"].sum().to_dict()
    cal_days = pd.date_range(start, end)
    cal_df = pd.DataFrame({"date": cal_days})
    cal_df["tss"] = cal_df["date"].dt.date.map(daily_tss).fillna(0)
    cal_df["dow"] = cal_df["date"].dt.dayofweek  # 0=Mon
    cal_df["week_of_year"] = cal_df["date"].dt.isocalendar().week
    cal_df["week_label"] = cal_df["date"].dt.strftime("%b %d")

    # Reshape to grid: rows = day of week, cols = week
    cal_df["week_idx"] = ((cal_df["date"] - cal_df["date"].min()).dt.days // 7).astype(int)
    pivot = cal_df.pivot_table(index="dow", columns="week_idx", values="tss", fill_value=0)
    week_labels = cal_df.groupby("week_idx")["date"].min().dt.strftime("%b %d").tolist()
    dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    fig_cal = go.Figure(go.Heatmap(
        z=pivot.values,
        x=week_labels,
        y=dow_labels,
        colorscale=[[0, "#1C1C1C"], [0.2, "#3D2F0E"], [0.5, "#7A5C18"],
                    [0.8, "#C99022"], [1.0, COLORS["gold"]]],
        showscale=True,
        colorbar=dict(title="TSS"),
        hovertemplate="%{y} %{x}<br>TSS: %{z:.0f}<extra></extra>",
    ))
    apply_theme(fig_cal, height=320)
    fig_cal.update_layout(xaxis=dict(side="top"), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig_cal, use_container_width=True)

    # Activity type mix
    st.subheader("Activity Mix (Last 28 Days)")
    mix = last_28.groupby("activity_type").agg(
        sessions=("date", "count"),
        hours=("duration_min", lambda s: s.sum() / 60),
        miles=("distance_miles", "sum"),
    ).reset_index().sort_values("hours", ascending=False)
    mix_renamed = mix.rename(columns={"activity_type": "Type", "sessions": "Sessions",
                                      "hours": "Hours", "miles": "Miles"})
    st.dataframe(mix_renamed, use_container_width=True, hide_index=True,
                 height=full_height(len(mix_renamed)))

# ── Sessions table ──────────────────────────────────────────────────────────
with tab_sessions:
    st.subheader("Recent Sessions")
    show = df.sort_values("date", ascending=False).head(30).copy()
    show["date"] = show["date"].dt.strftime("%Y-%m-%d")
    show["hours"] = (show["duration_min"] / 60).round(2)
    show["distance_miles"] = show["distance_miles"].round(1)
    show_cols = ["date", "activity_type", "hours", "distance_miles", "elevation_ft",
                 "avg_hr_bpm", "max_hr_bpm", "avg_power_watts", "tss", "zone2_min", "notes"]
    sessions_show = show[show_cols]
    st.dataframe(sessions_show, use_container_width=True, hide_index=True,
                 height=full_height(len(sessions_show)))
    st.caption(f"{len(sessions_show)} row(s)")


with st.expander("📚 Sources Informing Design", expanded=False):
    st.markdown("""
- **Seiler, S.** *What is best practice for training intensity and duration distribution in
  endurance athletes?* — the polarized-training (Z1/Z2 vs Z4/Z5) literature underpinning the
  Z1–Z5 zone definitions used on this page.
  [pubmed.ncbi.nlm.nih.gov/20861519](https://pubmed.ncbi.nlm.nih.gov/20861519/)
- **Laursen, P. & Buchheit, M.** *Science and Application of High-Intensity Interval Training*
  (Human Kinetics, 2019) — physiological basis for the Z4/Z5 categorization and HIIT dosing.
- **American Heart Association** — adult aerobic activity guidance: ≥150 min moderate or
  ≥75 min vigorous per week. [heart.org](https://www.heart.org/en/healthy-living/fitness/fitness-basics/aha-recs-for-physical-activity-in-adults)
- **Attia, P.** *Outlive*, Ch. 12 — practical zone-based programming for longevity, including
  the case for spending the bulk of weekly volume in Z2.
""")
