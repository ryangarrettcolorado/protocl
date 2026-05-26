"""Body Composition — InBody trends, recomp tracking, segmental analysis."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data, append_row
from modules.charts import COLORS, apply_theme, metric_card_html


st.set_page_config(page_title="Body Composition · Protocōl", page_icon="⚗️", layout="wide")

from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Body Composition")
    st.caption("Recomposition tracking · InBody scans · lean vs fat trajectory")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.inbody.copy()

if df.empty:
    st.info("No InBody scans logged yet. Add one below.")
    st.stop()

df = df.sort_values("date").reset_index(drop=True)
latest = df.iloc[-1]
first = df.iloc[0]
prev = df.iloc[-2] if len(df) >= 2 else first

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
weight_delta = latest["weight_lbs"] - first["weight_lbs"]
lean_delta = latest["lean_mass_lbs"] - first["lean_mass_lbs"]
bf_delta = latest["body_fat_pct"] - first["body_fat_pct"]
fat_mass_delta = latest["body_fat_mass_lbs"] - first["body_fat_mass_lbs"]

kpis = [
    ("BODY FAT %", f"{latest['body_fat_pct']:.1f}%", f"{bf_delta:+.1f} pts vs start", bf_delta < 0),
    ("LEAN MASS", f"{latest['lean_mass_lbs']:.1f} lb", f"{lean_delta:+.1f} lb vs start", lean_delta > 0),
    ("WEIGHT", f"{latest['weight_lbs']:.1f} lb", f"{weight_delta:+.1f} lb vs start", None),
    ("FAT MASS", f"{latest['body_fat_mass_lbs']:.1f} lb", f"{fat_mass_delta:+.1f} lb vs start", fat_mass_delta < 0),
    ("VISCERAL FAT", f"{int(latest['visceral_fat_level'])}", "level (target ≤10)", latest["visceral_fat_level"] <= 10),
    ("BMR", f"{int(latest['bmr_kcal']):,}", "kcal/day", None),
]

cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_trends, tab_recomp, tab_segmental, tab_table, tab_add = st.tabs(
    ["📈 Trends", "🔀 Recomp View", "📊 Composition", "📋 All Scans", "➕ Add Scan"]
)

# ── Trends ──────────────────────────────────────────────────────────────────
with tab_trends:
    st.subheader("12-Month Trajectory")

    # Dual-axis: weight + body fat %
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["weight_lbs"],
        name="Weight (lb)", mode="lines+markers",
        line=dict(color=COLORS["gold"], width=3),
        marker=dict(size=8),
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["body_fat_pct"],
        name="Body Fat %", mode="lines+markers",
        line=dict(color=COLORS["chart_series"][1], width=3),
        marker=dict(size=8),
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=df["lean_mass_lbs"],
        name="Lean Mass (lb)", mode="lines+markers",
        line=dict(color=COLORS["success"], width=3, dash="dot"),
        marker=dict(size=8),
        yaxis="y",
    ))
    apply_theme(fig, height=420)
    fig.update_layout(
        yaxis=dict(title="Pounds", gridcolor="#2A2A2A"),
        yaxis2=dict(title="Body Fat %", overlaying="y", side="right", gridcolor="rgba(0,0,0,0)"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Skeletal Muscle vs Body Fat Mass")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=df["date"], y=df["skeletal_muscle_mass_lbs"],
        name="Skeletal Muscle", mode="lines+markers",
        line=dict(color=COLORS["gold"], width=3),
        fill="tozeroy", fillcolor="rgba(255,182,18,0.08)",
    ))
    fig2.add_trace(go.Scatter(
        x=df["date"], y=df["body_fat_mass_lbs"],
        name="Body Fat Mass", mode="lines+markers",
        line=dict(color=COLORS["danger"], width=3),
        fill="tozeroy", fillcolor="rgba(244,67,54,0.08)",
    ))
    apply_theme(fig2, height=340)
    fig2.update_layout(
        yaxis=dict(title="Pounds"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)

# ── Recomp view ─────────────────────────────────────────────────────────────
with tab_recomp:
    st.subheader("Recomposition Scorecard")
    st.caption(f"Window: {first['date'].strftime('%b %Y')} → {latest['date'].strftime('%b %Y')} ({(latest['date'] - first['date']).days} days)")

    recomp_grade = (
        "🟢 Successful recomp" if (lean_delta > 0 and fat_mass_delta < 0)
        else ("🟡 Cutting (lean static)" if (lean_delta >= -1 and fat_mass_delta < 0)
        else ("🟠 Bulking (gained lean + fat)" if (lean_delta > 0 and fat_mass_delta > 0)
        else "🔴 Reverse recomp (lost lean, gained fat)"))
    )
    st.markdown(f"### {recomp_grade}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Lean mass change**")
        st.metric("Skeletal muscle", f"{latest['skeletal_muscle_mass_lbs']:.1f} lb",
                  f"{latest['skeletal_muscle_mass_lbs'] - first['skeletal_muscle_mass_lbs']:+.1f} lb")
    with c2:
        st.markdown("**Fat mass change**")
        st.metric("Body fat mass", f"{latest['body_fat_mass_lbs']:.1f} lb",
                  f"{fat_mass_delta:+.1f} lb", delta_color="inverse")
    with c3:
        st.markdown("**Net body fat %**")
        st.metric("Body fat %", f"{latest['body_fat_pct']:.1f}%",
                  f"{bf_delta:+.1f} pts", delta_color="inverse")

    # Lean : Fat ratio over time
    st.subheader("Lean-to-Fat Ratio")
    df_ratio = df.copy()
    df_ratio["lean_fat_ratio"] = df_ratio["lean_mass_lbs"] / df_ratio["body_fat_mass_lbs"]
    fig_ratio = go.Figure()
    fig_ratio.add_trace(go.Scatter(
        x=df_ratio["date"], y=df_ratio["lean_fat_ratio"],
        mode="lines+markers",
        line=dict(color=COLORS["gold"], width=3),
        marker=dict(size=10),
        fill="tozeroy", fillcolor="rgba(255,182,18,0.05)",
        name="Lean : Fat",
    ))
    apply_theme(fig_ratio, height=300)
    fig_ratio.update_layout(yaxis=dict(title="Lean lbs / Fat lbs"))
    st.plotly_chart(fig_ratio, use_container_width=True)

# ── Segmental / composition ─────────────────────────────────────────────────
with tab_segmental:
    st.subheader("Latest Composition Breakdown")
    st.caption(latest["date"].strftime("Scan from %b %d, %Y"))

    other_lean = max(latest["lean_mass_lbs"] - latest["skeletal_muscle_mass_lbs"], 0)
    fig_donut = go.Figure(go.Pie(
        labels=["Skeletal Muscle", "Other Lean (organs, bone)", "Body Fat", "Water (in lean)"],
        values=[
            latest["skeletal_muscle_mass_lbs"],
            other_lean,
            latest["body_fat_mass_lbs"],
            max(latest["total_body_water_lbs"] - latest["skeletal_muscle_mass_lbs"] * 0.73, 0),
        ],
        hole=0.55,
        marker=dict(colors=[COLORS["gold"], COLORS["chart_series"][2],
                            COLORS["danger"], COLORS["chart_series"][1]]),
        textinfo="label+percent",
    ))
    apply_theme(fig_donut, height=420)
    fig_donut.update_layout(showlegend=False, margin=dict(t=20, b=20))
    st.plotly_chart(fig_donut, use_container_width=True)

    # Water + BMR detail
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Total Body Water**")
        st.metric("Water", f"{latest['total_body_water_lbs']:.1f} lb",
                  f"{latest['total_body_water_lbs'] - first['total_body_water_lbs']:+.1f} lb vs start")
        st.caption("Hydration tracks closely with lean mass — typical ratio is 60–70% of lean.")
    with c2:
        st.markdown("**Basal Metabolic Rate**")
        bmr_delta = latest["bmr_kcal"] - first["bmr_kcal"]
        st.metric("BMR", f"{int(latest['bmr_kcal']):,} kcal/day",
                  f"{bmr_delta:+.0f} kcal vs start")
        st.caption("BMR rises with lean mass — a recomp signal that doesn't lie.")

# ── Full table ──────────────────────────────────────────────────────────────
with tab_table:
    st.subheader("All InBody Scans")
    display_df = df.copy()
    display_df["date"] = display_df["date"].dt.strftime("%Y-%m-%d")
    cols_show = ["date", "weight_lbs", "body_fat_pct", "skeletal_muscle_mass_lbs",
                 "lean_mass_lbs", "body_fat_mass_lbs", "visceral_fat_level",
                 "total_body_water_lbs", "bmr_kcal", "source", "notes"]
    st.dataframe(display_df[cols_show], use_container_width=True, hide_index=True)

# ── Add scan ────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Log a New InBody Scan")
    with st.form("new_scan"):
        c1, c2, c3 = st.columns(3)
        with c1:
            scan_date = st.date_input("Scan date")
            weight = st.number_input("Weight (lb)", min_value=80.0, max_value=400.0, value=float(latest["weight_lbs"]), step=0.1)
            bf_pct = st.number_input("Body fat %", min_value=3.0, max_value=50.0, value=float(latest["body_fat_pct"]), step=0.1)
        with c2:
            smm = st.number_input("Skeletal muscle mass (lb)", min_value=20.0, max_value=200.0, value=float(latest["skeletal_muscle_mass_lbs"]), step=0.1)
            lean = st.number_input("Lean mass (lb)", min_value=40.0, max_value=300.0, value=float(latest["lean_mass_lbs"]), step=0.1)
            fat_mass = st.number_input("Body fat mass (lb)", min_value=2.0, max_value=200.0, value=float(latest["body_fat_mass_lbs"]), step=0.1)
        with c3:
            visceral = st.number_input("Visceral fat level", min_value=1, max_value=30, value=int(latest["visceral_fat_level"]))
            water = st.number_input("Total body water (lb)", min_value=30.0, max_value=200.0, value=float(latest["total_body_water_lbs"]), step=0.1)
            bmr = st.number_input("BMR (kcal)", min_value=800, max_value=4000, value=int(latest["bmr_kcal"]))
        notes = st.text_input("Notes")
        if st.form_submit_button("Save scan", use_container_width=True):
            append_row("inbody.csv", {
                "date": scan_date.isoformat(),
                "weight_lbs": weight,
                "skeletal_muscle_mass_lbs": smm,
                "body_fat_mass_lbs": fat_mass,
                "body_fat_pct": bf_pct,
                "visceral_fat_level": visceral,
                "lean_mass_lbs": lean,
                "total_body_water_lbs": water,
                "bmr_kcal": bmr,
                "source": "manual",
                "notes": notes,
            })
            st.success("Scan saved.")
            st.rerun()
