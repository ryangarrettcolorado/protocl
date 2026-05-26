"""Zone 2 / VO2max — the Attia longevity dose."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data
from modules.charts import COLORS, apply_theme, metric_card_html


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Zone 2 + VO2max")
    st.caption("Mitochondrial base · zone-2 dose · VO2max trend — the longevity engine")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
training = data.training.copy()
wearables = data.wearables.copy()

if training.empty:
    st.info("No training sessions logged yet.")
    st.stop()

training = training.sort_values("date").reset_index(drop=True)
training["week"] = training["date"].dt.to_period("W").dt.start_time

TODAY = pd.Timestamp("2026-05-25")
last_7 = training[training["date"] >= TODAY - pd.Timedelta(days=7)]
last_28 = training[training["date"] >= TODAY - pd.Timedelta(days=28)]

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
z2_7d = last_7["zone2_min"].sum()
z2_28d = last_28["zone2_min"].sum()
z2_target_weekly = 180  # 3hr/week Attia minimum
adherence = min(z2_7d / z2_target_weekly * 100, 100) if z2_target_weekly else 0

latest_vo2 = wearables["vo2_max_ml_kg_min"].dropna().iloc[-1] if (not wearables.empty and wearables["vo2_max_ml_kg_min"].notna().any()) else None
first_vo2 = wearables["vo2_max_ml_kg_min"].dropna().iloc[0] if (not wearables.empty and wearables["vo2_max_ml_kg_min"].notna().any()) else None
vo2_delta = (latest_vo2 - first_vo2) if (latest_vo2 and first_vo2) else None

# Z2 percentage of total
total_min_28 = last_28["duration_min"].sum()
z2_pct = (z2_28d / total_min_28 * 100) if total_min_28 else 0

kpis = [
    ("7D ZONE 2", f"{int(z2_7d)} min", f"target ≥{z2_target_weekly} min/wk", z2_7d >= z2_target_weekly),
    ("Z2 ADHERENCE", f"{adherence:.0f}%", "of weekly target", adherence >= 80),
    ("28D Z2 VOLUME", f"{z2_28d/60:.1f} h", f"{z2_pct:.0f}% of training", None),
    ("VO2 MAX", f"{latest_vo2:.1f}" if latest_vo2 else "—",
     f"{vo2_delta:+.1f} vs start" if vo2_delta is not None else "ml/kg/min",
     vo2_delta is not None and vo2_delta > 0),
    ("Z2 SESSIONS 28D", f"{(last_28['zone2_min'] > 0).sum()}", "with any Z2 time", None),
    ("BEST WEEK 28D", f"{int(last_28.groupby('week')['zone2_min'].sum().max() if not last_28.empty else 0)} min",
     "Zone 2 peak", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_dose, tab_vo2, tab_efficiency, tab_protocol = grouped_sections(
    ["⏱️ Z2 Dose", "❤️ VO2max", "⚙️ Efficiency", "📖 Protocol Notes"]
)

# ── Z2 dose ─────────────────────────────────────────────────────────────────
with tab_dose:
    st.subheader("Weekly Zone 2 Minutes")
    st.caption("Attia minimum is 3 hours / week of true Z2 (talking-pace, nose-breathing).")

    weekly = training.groupby("week").agg(
        z2=("zone2_min", "sum"),
        total=("duration_min", "sum"),
        sessions=("date", "count"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=weekly["week"], y=weekly["z2"],
        name="Zone 2 minutes",
        marker=dict(color=[COLORS["success"] if z >= z2_target_weekly else COLORS["gold"]
                           for z in weekly["z2"]]),
        text=[f"{int(z)}m" for z in weekly["z2"]],
        textposition="outside",
    ))
    fig.add_hline(y=z2_target_weekly, line=dict(color=COLORS["chart_series"][1], width=2, dash="dash"),
                  annotation_text=f"Attia min ({z2_target_weekly} min)", annotation_position="right")
    fig.add_hline(y=240, line=dict(color=COLORS["success"], width=1, dash="dot"),
                  annotation_text="Optimal (240 min)", annotation_position="right")
    apply_theme(fig, height=380)
    fig.update_layout(yaxis=dict(title="Minutes"), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

    # Streak analysis
    weekly["hit_target"] = weekly["z2"] >= z2_target_weekly
    streak = 0
    for hit in weekly["hit_target"].iloc[::-1]:
        if hit: streak += 1
        else: break
    total_weeks = len(weekly)
    target_weeks = weekly["hit_target"].sum()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Current streak", f"{streak} weeks", "consecutive ≥180 min")
    with c2:
        st.metric("Hit rate", f"{target_weeks}/{total_weeks}", f"{target_weeks/total_weeks*100:.0f}% of weeks")
    with c3:
        st.metric("Avg week", f"{weekly['z2'].mean():.0f} min", f"all weeks")

# ── VO2max ──────────────────────────────────────────────────────────────────
with tab_vo2:
    st.subheader("VO2max Trend")
    st.caption("From wearable estimate — go from middle quintile to top quartile for ~3x longevity benefit.")

    if not wearables.empty and wearables["vo2_max_ml_kg_min"].notna().any():
        w = wearables.dropna(subset=["vo2_max_ml_kg_min"]).sort_values("date")
        # 7-day rolling average to smooth daily noise
        w["vo2_smooth"] = w["vo2_max_ml_kg_min"].rolling(7, min_periods=1).mean()
        fig_vo2 = go.Figure()
        fig_vo2.add_trace(go.Scatter(
            x=w["date"], y=w["vo2_max_ml_kg_min"],
            mode="markers", name="Daily",
            marker=dict(color=COLORS["chart_series"][1], size=6, opacity=0.4),
        ))
        fig_vo2.add_trace(go.Scatter(
            x=w["date"], y=w["vo2_smooth"],
            mode="lines", name="7d Rolling",
            line=dict(color=COLORS["gold"], width=3),
        ))
        # Age-graded reference bands for ~42yo male
        fig_vo2.add_hrect(y0=49, y1=60, fillcolor="rgba(76,175,80,0.08)", line=dict(width=0),
                           annotation_text="Excellent (top 5%)", annotation_position="top left")
        fig_vo2.add_hrect(y0=43, y1=49, fillcolor="rgba(255,182,18,0.06)", line=dict(width=0),
                           annotation_text="Good", annotation_position="top left")
        fig_vo2.add_hrect(y0=36, y1=43, fillcolor="rgba(255,152,0,0.05)", line=dict(width=0))
        apply_theme(fig_vo2, height=420)
        fig_vo2.update_layout(yaxis=dict(title="ml/kg/min"),
                               legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(fig_vo2, use_container_width=True)

        cur = w["vo2_max_ml_kg_min"].iloc[-1]
        if cur >= 49:
            band = "🟢 **Excellent** — top 5% age-graded"
        elif cur >= 43:
            band = "🟡 **Good** — 75th-95th percentile"
        elif cur >= 36:
            band = "🟠 **Average** — middle quintile"
        else:
            band = "🔴 **Below avg** — bottom quartile"
        st.markdown(f"**Current band:** {band}")
    else:
        st.info("No VO2max data in wearables.csv yet.")

# ── Efficiency ──────────────────────────────────────────────────────────────
with tab_efficiency:
    st.subheader("Aerobic Efficiency Markers")
    st.caption("Watts/HR (cycling) or pace/HR — efficiency rising = fitness gain.")

    rides = training[(training["activity_type"] == "ride") & (training["avg_power_watts"].notna())].copy()
    if not rides.empty:
        rides["wpb"] = rides["avg_power_watts"] / rides["avg_hr_bpm"]
        rides["week"] = rides["date"].dt.to_period("W").dt.start_time
        wk_eff = rides.groupby("week").agg(
            wpb=("wpb", "mean"),
            power=("avg_power_watts", "mean"),
            hr=("avg_hr_bpm", "mean"),
        ).reset_index()

        fig_eff = go.Figure()
        fig_eff.add_trace(go.Scatter(
            x=wk_eff["week"], y=wk_eff["wpb"],
            mode="lines+markers", name="Watts / HR",
            line=dict(color=COLORS["gold"], width=3),
            marker=dict(size=8),
        ))
        apply_theme(fig_eff, height=320)
        fig_eff.update_layout(yaxis=dict(title="Watts per BPM"))
        st.plotly_chart(fig_eff, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Avg power (rides)", f"{rides['avg_power_watts'].mean():.0f} W")
        with c2:
            st.metric("Avg HR (rides)", f"{rides['avg_hr_bpm'].mean():.0f} bpm")
        with c3:
            efficiency_delta = wk_eff["wpb"].iloc[-4:].mean() - wk_eff["wpb"].iloc[:4].mean()
            st.metric("Eff trend", f"{efficiency_delta:+.2f} W/bpm",
                      "first 4 → last 4 weeks")
    else:
        st.info("No power-meter data — Watts/HR efficiency requires logged avg_power_watts.")

# ── Protocol notes ──────────────────────────────────────────────────────────
with tab_protocol:
    st.markdown("""
### Why Zone 2 Matters

**Zone 2** (≈60–70% of max HR, conversational pace) builds mitochondrial density
and fat-oxidation capacity. The Attia / Inigo San Millán argument:

- **3 hr/wk minimum** to maintain
- **4–6 hr/wk** for elite-trending metabolic flexibility
- True Z2 = **nose-breathing pace** — if you can't hold a conversation, it's Z3

### Z2 + VO2max → All-cause Mortality

[Mandsager 2018 (JAMA)](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2707428):
moving from the bottom quartile of cardiorespiratory fitness to the top quartile
is associated with a **~5x reduction** in all-cause mortality — larger than any
drug. Top-decile vs bottom-decile is even more pronounced.

### Practical Zone 2 Checks

| Method | Z2 Signal |
|---|---|
| Lactate meter | 1.7–2.0 mmol/L sustained |
| Nose-breathing | Can hold full nasal for 30+ min |
| Talk test | Full sentences, no gasping |
| HR | ~65–75% of max, very stable |
| Power | If known, ~55–75% of FTP |

### Common Failure Mode

Most "zone 2" rides are actually Z3 — you ride too hard. **Slow down.**
The point is volume of low-intensity mitochondrial stimulus, not feeling worked.
""")
