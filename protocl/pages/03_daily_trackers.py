"""Daily Trackers — macros, hydration, sleep, subjective markers."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data, append_row
from modules.charts import COLORS, apply_theme, metric_card_html, full_height
from modules.time_range import render_time_range_selector, filter_by_range


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Daily Trackers")
    st.caption("Macros · hydration · sleep · subjective state — the daily log")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.daily_log.copy()

TODAY = pd.Timestamp("2026-05-25")

if not df.empty:
    df = df.sort_values("date").reset_index(drop=True)
    tr_start, tr_end, tr_preset = render_time_range_selector("daily_trackers", default_preset="30d")
    df = filter_by_range(df, "date", tr_start, tr_end).sort_values("date").reset_index(drop=True)

IS_EMPTY = df.empty
if IS_EMPTY:
    last_7 = df
    last_28 = df
else:
    # `last_7` / `last_28` stay relative to TODAY regardless of the page time
    # range so the headline KPI windows remain meaningful (and aren't widened
    # when the user picks "All time").
    last_7 = df[df["date"] >= TODAY - pd.Timedelta(days=7)]
    last_28 = df[df["date"] >= TODAY - pd.Timedelta(days=28)]

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
def _avg(col_name, suffix=""):
    if IS_EMPTY or last_7[col_name].isna().all():
        return "—"
    return f"{last_7[col_name].mean():.0f}{suffix}"


def _pos(col_name, threshold):
    if IS_EMPTY or last_7[col_name].isna().all():
        return None
    return last_7[col_name].mean() >= threshold


kpis = [
    ("CALORIES 7D", _avg("calories_kcal"), "daily avg", None),
    ("PROTEIN 7D", _avg("protein_g", " g"),
        "" if IS_EMPTY else f"{last_7['protein_g'].mean()/195*1000:.0f} mg/lb",
        _pos("protein_g", 180)),
    ("CARBS 7D", _avg("carbs_g", " g"), "daily avg", None),
    ("FAT 7D", _avg("fat_g", " g"), "daily avg", None),
    ("FIBER 7D", _avg("fiber_g", " g"), "target ≥30 g", _pos("fiber_g", 30)),
    ("WATER 7D", _avg("water_oz", " oz"), "target ≥80 oz", _pos("water_oz", 80)),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

if IS_EMPTY:
    st.info("No daily logs yet — add your first entry in the **Log Today** tab below.")

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_macros, tab_sleep, tab_hydration, tab_log, tab_add = grouped_sections(
    ["🍽️ Macros", "🌙 Sleep", "💧 Hydration", "📋 Log", "➕ Log Today"]
)

EMPTY_HINT = "No daily logs yet — use the **➕ Log Today** tab to add your first entry. Charts will populate as soon as you save one day."


# ── Macros ──────────────────────────────────────────────────────────────────
with tab_macros:
    st.subheader("Daily Macro Breakdown")
    if IS_EMPTY:
        st.info(EMPTY_HINT)
    else:
        df["cal_protein"] = df["protein_g"] * 4
        df["cal_carbs"] = df["carbs_g"] * 4
        df["cal_fat"] = df["fat_g"] * 9

        fig = go.Figure()
        fig.add_trace(go.Bar(x=df["date"], y=df["cal_protein"], name="Protein",
                              marker=dict(color=COLORS["gold"])))
        fig.add_trace(go.Bar(x=df["date"], y=df["cal_carbs"], name="Carbs",
                              marker=dict(color=COLORS["chart_series"][1])))
        fig.add_trace(go.Bar(x=df["date"], y=df["cal_fat"], name="Fat",
                              marker=dict(color=COLORS["chart_series"][2])))
        fig.update_layout(barmode="stack")
        apply_theme(fig, height=380)
        fig.update_layout(
            yaxis=dict(title="kcal"),
            legend=dict(orientation="h", y=1.1, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Last 7 Days — Energy Source Mix")
        p = last_7["protein_g"].sum() * 4
        c = last_7["carbs_g"].sum() * 4
        f = last_7["fat_g"].sum() * 9
        fig_donut = go.Figure(go.Pie(
            labels=["Protein", "Carbs", "Fat"],
            values=[p, c, f],
            hole=0.55,
            marker=dict(colors=[COLORS["gold"], COLORS["chart_series"][1], COLORS["chart_series"][2]]),
            textinfo="label+percent",
        ))
        apply_theme(fig_donut, height=340)
        fig_donut.update_layout(showlegend=False)

        c1, c2 = st.columns([2, 3])
        with c1:
            st.plotly_chart(fig_donut, use_container_width=True)
        with c2:
            st.markdown("**Daily averages — last 7 days**")
            total_kcal = max(p + c + f, 1)
            avg_df = pd.DataFrame({
                "Macro": ["Protein", "Carbs", "Fat", "Fiber", "Calories"],
                "Per Day": [
                    f"{last_7['protein_g'].mean():.0f} g",
                    f"{last_7['carbs_g'].mean():.0f} g",
                    f"{last_7['fat_g'].mean():.0f} g",
                    f"{last_7['fiber_g'].mean():.0f} g",
                    f"{last_7['calories_kcal'].mean():.0f} kcal",
                ],
                "% of kcal": [
                    f"{p / total_kcal * 100:.0f}%",
                    f"{c / total_kcal * 100:.0f}%",
                    f"{f / total_kcal * 100:.0f}%",
                    "—",
                    "100%",
                ],
            })
            st.dataframe(avg_df, use_container_width=True, hide_index=True,
                         height=full_height(len(avg_df)))


# ── Sleep (from daily log) ──────────────────────────────────────────────────
with tab_sleep:
    st.subheader("Sleep Duration + Subjective Quality")
    if IS_EMPTY:
        st.info(EMPTY_HINT)
        st.caption("Tip: your Apple Watch sleep stages are already in **Wearables**. This view captures your *subjective* sleep quality alongside it.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["date"], y=df["sleep_hrs"],
            name="Sleep hours",
            marker=dict(color=COLORS["chart_series"][4], opacity=0.7),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["sleep_quality_1_10"],
            mode="lines+markers", name="Quality (1-10)",
            line=dict(color=COLORS["gold"], width=3),
            yaxis="y2",
        ))
        fig.add_hline(y=7.5, line=dict(color=COLORS["text_primary"], width=1, dash="dash"))
        apply_theme(fig, height=380)
        fig.update_layout(
            yaxis=dict(title="Hours"),
            yaxis2=dict(title="Quality 1-10", overlaying="y", side="right", range=[0, 10]),
            legend=dict(orientation="h", y=1.1, x=0),
        )
        st.plotly_chart(fig, use_container_width=True)

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Avg Sleep 28d", f"{last_28['sleep_hrs'].mean():.1f} h")
        with c2:
            st.metric("Avg Quality 28d", f"{last_28['sleep_quality_1_10'].mean():.1f}/10")
        with c3:
            nights_7plus = (last_28["sleep_hrs"] >= 7).sum()
            st.metric("7h+ nights 28d", f"{nights_7plus}/{len(last_28)}")


# ── Hydration ───────────────────────────────────────────────────────────────
with tab_hydration:
    st.subheader("Hydration — Water Intake")
    if IS_EMPTY:
        st.info(EMPTY_HINT)
    else:
        df["water_7d"] = df["water_oz"].rolling(7, min_periods=1).mean()
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["date"], y=df["water_oz"],
            marker=dict(color=COLORS["chart_series"][1], opacity=0.45),
            name="Daily oz",
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["water_7d"],
            mode="lines", name="7d avg",
            line=dict(color=COLORS["chart_series"][1], width=3),
        ))
        fig.add_hline(y=80, line=dict(color=COLORS["success"], width=1, dash="dot"),
                      annotation_text="80 oz target", annotation_position="right")
        fig.add_hline(y=120, line=dict(color=COLORS["gold"], width=1, dash="dot"),
                      annotation_text="120 oz active days", annotation_position="right")
        apply_theme(fig, height=340)
        fig.update_layout(yaxis=dict(title="Ounces"),
                           legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(fig, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Avg Water 28d", f"{last_28['water_oz'].mean():.0f} oz")
        with c2:
            target_hits = (last_28["water_oz"] >= 80).sum()
            st.metric("80oz+ days 28d", f"{target_hits}/{len(last_28)}")


# ── Log table ───────────────────────────────────────────────────────────────
with tab_log:
    st.subheader("Daily Log — Last 30 Days")
    if IS_EMPTY:
        st.info(EMPTY_HINT)
    else:
        show = df.sort_values("date", ascending=False).head(30).copy()
        show["date"] = show["date"].dt.strftime("%Y-%m-%d")
        cols_show = ["date", "calories_kcal", "protein_g", "carbs_g", "fat_g",
                     "fiber_g", "water_oz", "sleep_hrs", "sleep_quality_1_10", "notes"]
        cols_df = show[cols_show]
        st.dataframe(cols_df, use_container_width=True, hide_index=True,
                     height=full_height(len(cols_df)))
        st.caption(f"{len(cols_df)} row(s)")


# ── Add today's log ─────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Log Today")
    st.caption("Quick daily check-in. Fields are remembered as defaults for the next entry.")
    with st.form("daily_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        with c1:
            log_date = st.date_input("Date", value=pd.Timestamp.today().date())
            cals = st.number_input("Calories (kcal)", min_value=0, max_value=8000, value=2500, step=50)
            protein = st.number_input("Protein (g)", min_value=0, max_value=500, value=180, step=5)
        with c2:
            carbs = st.number_input("Carbs (g)", min_value=0, max_value=800, value=220, step=5)
            fat = st.number_input("Fat (g)", min_value=0, max_value=300, value=85, step=5)
            fiber = st.number_input("Fiber (g)", min_value=0, max_value=100, value=30, step=1)
        with c3:
            water = st.number_input("Water (oz)", min_value=0, max_value=300, value=80, step=4)
            sleep = st.number_input("Sleep (hrs)", min_value=0.0, max_value=14.0, value=7.5, step=0.25)
            quality = st.slider("Sleep quality 1-10", 1, 10, 7)

        st.markdown("**Subjective markers** (optional)")
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            mood = st.slider("Mood 1-10", 1, 10, 7)
        with s2:
            energy = st.slider("Energy 1-10", 1, 10, 7)
        with s3:
            stress = st.slider("Stress 1-10", 1, 10, 4)
        with s4:
            soreness = st.slider("Soreness 1-10", 1, 10, 3)

        notes = st.text_area(
            "Notes",
            placeholder="Free text — what felt off, what felt great, training, meds taken, etc.",
            height=80,
        )
        if st.form_submit_button("Save entry", use_container_width=True, type="primary"):
            # Encode subjective markers into notes so the existing CSV schema is preserved.
            subj_str = f"[mood={mood} energy={energy} stress={stress} soreness={soreness}]"
            full_notes = f"{subj_str} {notes}".strip()
            append_row("daily_log.csv", {
                "date": log_date.isoformat(),
                "calories_kcal": cals,
                "protein_g": protein,
                "carbs_g": carbs,
                "fat_g": fat,
                "fiber_g": fiber,
                "water_oz": water,
                "sleep_hrs": sleep,
                "sleep_quality_1_10": quality,
                "notes": full_notes,
            })
            st.success(f"Saved entry for {log_date.isoformat()}.")
            st.rerun()
