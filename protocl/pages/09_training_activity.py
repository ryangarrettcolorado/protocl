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
from explainers.ui import explainer_block


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
tab_load, tab_intensity, tab_calendar, tab_sessions = grouped_sections(
    ["📈 Load & Volume", "🔥 Intensity", "🗓️ Calendar", "📋 Sessions"]
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

    explainer_block("training_volume_by_week", chart_data={
        "weeks": [
            {"week": w.strftime("%Y-%m-%d"), "hours": round(float(h), 2),
             "tss": round(float(t), 0), "sessions": int(s)}
            for w, h, t, s in zip(weekly["week"], weekly["hours"],
                                  weekly["tss"], weekly["sessions"])
        ][-16:],
    })

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
        # Heat ramps from surface → mist → primary teal so the gradient
        # reads in both light and dark modes (chart_series follows theme).
        colorscale=[[0, COLORS["surface"]],
                    [0.25, COLORS["chart_series"][3]],  # mist
                    [0.5,  COLORS["chart_series"][2]],  # deep teal
                    [0.75, COLORS["chart_series"][0]],  # series c1
                    [1.0,  COLORS["primary"]]],
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
