"""🌙 Sleep — v3.0 sleep coaching dashboard.

Covers spec sections A3–A9 in one scrollable page:
  - Today's verdict block (score + formula expander)
  - 7-day score trend
  - Sleep debt accumulator
  - Stage breakdown (last night) + stage trends across window
  - HRV + RHR overnight charts
  - Sleep consistency scatter
  - Hypnogram drilldown (A4) — same page, expander (see DECISIONS.md)
  - Wind-down plan (A5) + Caffeine timing (A6) + Smart-alarm window (A7)
  - Stress-Sleep correlations (A8)
  - Protocol overlays (A9)
  - Sources expander
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.charts import COLORS, apply_theme
from modules.data_loader import load_data
from modules.llm import llm_badge
from explainers.ui import explainer_block
from modules.sleep_data import (
    SleepNight,
    compute_baseline,
    get_latest_night,
    load_journal,
    load_sleep_nights,
)
from modules.sleep_need import compute_sleep_need
from modules.sleep_score import compute_sleep_score, verdict
from modules.time_range import filter_by_range, render_time_range_selector
from modules.theme import inject_css
from modules.caffeine import (
    PRESETS as CAFFEINE_PRESETS,
    decay_curve,
    load_caffeine_log,
    log_caffeine,
    recommend_cutoff,
    remaining_mg,
)


inject_css()


CHART_SERIES = COLORS["chart_series"]


def _color_for_verdict(v: str) -> str:
    return {"ready": "#4CAF50", "moderate": "#FFD54F", "low": "#EF5350"}.get(v, COLORS["text_muted"])


def _fmt_hm(minutes: float | int | None) -> str:
    if minutes is None or pd.isna(minutes):
        return "—"
    m = int(minutes)
    return f"{m // 60}h {m % 60:02d}m"


# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_badge = st.columns([6, 1.5])
with col_title:
    st.title("🌙 Sleep")
    st.caption("Bevel-quality sleep coaching · TRT + peptide + Anavar + Retatrutide-aware")
with col_badge:
    st.markdown(f"<div style='padding-top:18px;text-align:right;'>{llm_badge()}</div>",
                unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Data
# ────────────────────────────────────────────────────────────────────────────
data = load_data()
nights = load_sleep_nights(window_days=180)
baseline = compute_baseline(nights, days=28)
latest = nights[-1] if nights else None

# Sleep need for today
need_result = compute_sleep_need(
    nights=nights,
    wearables=data.wearables,
    training=data.training,
    bloodwork=data.bloodwork,
    calendar_events=[],
)
sleep_need_min = need_result["sleep_need_min"]


if latest is None:
    st.warning("No sleep data found in wearables.csv yet. Sync Apple Health to populate.")
    st.stop()


# ────────────────────────────────────────────────────────────────────────────
# A3.2 — Today's verdict block (hero)
# ────────────────────────────────────────────────────────────────────────────
score_result = compute_sleep_score(latest, baseline, sleep_need_min)
score = score_result["score"]
vdict = score_result["verdict"]
verdict_color = _color_for_verdict(vdict)
verdict_line = {
    "ready":    "Ready to train hard",
    "moderate": "Moderate — train smart",
    "low":      "Recovery day recommended",
}[vdict]

debt_min = max(0, sleep_need_min - (latest.total_asleep_min or 0))

hero_col1, hero_col2 = st.columns([1, 2])
with hero_col1:
    st.markdown(
        f"""<div style='border:2px solid {verdict_color};border-radius:14px;
        padding:24px 18px;text-align:center;background:{COLORS["steel_mid"]};'>
        <div style='font-size:0.85rem;color:{COLORS["text_muted"]};text-transform:uppercase;'>
        Tonight's Score</div>
        <div style='font-size:64px;font-weight:700;color:{verdict_color};line-height:1;'>
        {score:.0f}</div>
        <div style='color:{verdict_color};font-weight:600;margin-top:8px;'>{verdict_line}</div>
        </div>""",
        unsafe_allow_html=True,
    )

with hero_col2:
    st.markdown(f"### Last night: **{_fmt_hm(latest.total_asleep_min)}** of "
                f"**{_fmt_hm(sleep_need_min)}** needed")
    if debt_min > 0:
        st.markdown(f"Sleep debt: **{_fmt_hm(debt_min)}**")
    else:
        st.markdown("✓ Sleep need met")

    # Why need is what it is
    if need_result["adjustments"]:
        adj_lines = ["Base **8h** plus:"] + [
            f"- **+{a['minutes']} min** — {a['label']} ({a['reason']})"
            for a in need_result["adjustments"]
        ]
        st.markdown("\n".join(adj_lines))
    else:
        st.caption("Base 8h need — no adjustments applied today.")

with st.expander("📖 See formula"):
    st.markdown(
        f"""
        **Composite score** = weighted blend of four components:

        | Component | Weight | Score | Detail |
        |---|---|---|---|
        | Duration | 40% | {score_result['components']['duration']['score']} | {score_result['components']['duration']['value_min']} min of {score_result['components']['duration']['need_min']} min needed |
        | Depth / quality | 30% | {score_result['components']['depth_quality']['score']} | Deep {score_result['components']['depth_quality']['deep_pct']*100:.1f}% (target ≥15%) · REM {score_result['components']['depth_quality']['rem_pct']*100:.1f}% (target ≥20%) |
        | HRV | 20% | {score_result['components']['hrv']['score']} | {score_result['components']['hrv']['hrv']} ms vs 28d baseline {score_result['components']['hrv']['baseline']} |
        | Consistency | 10% | {score_result['components']['consistency']['score']} | Bed-time stddev: {score_result['components']['consistency']['bed_time_stddev_min']} min |

        **Verdict thresholds:** ready ≥80 · moderate 60–79 · low <60
        """
    )

st.divider()

# ────────────────────────────────────────────────────────────────────────────
# A3.3 — 7-day score trend
# ────────────────────────────────────────────────────────────────────────────
st.subheader("Last 7 nights")
trend_nights = nights[-7:]
trend_scores = []
for n in trend_nights:
    if n.total_asleep_min:
        sr = compute_sleep_score(n, baseline, sleep_need_min)
        trend_scores.append((n.date, sr["score"], sr["verdict"]))
    else:
        trend_scores.append((n.date, None, "none"))

if trend_scores:
    fig = go.Figure()
    fig.add_bar(
        x=[t[0] for t in trend_scores],
        y=[t[1] or 0 for t in trend_scores],
        marker_color=[_color_for_verdict(t[2]) if t[1] else "#444" for t in trend_scores],
        text=[f"{t[1]:.0f}" if t[1] is not None else "—" for t in trend_scores],
        textposition="outside",
    )
    fig.update_yaxes(range=[0, 105], title="Score")
    apply_theme(fig, height=280)
    st.plotly_chart(fig, use_container_width=True)
    explainer_block("sleep_score_trend", chart_data={
        "nights": [{"date": str(t[0]), "score": t[1], "verdict": t[2]} for t in trend_scores]
    })


# ────────────────────────────────────────────────────────────────────────────
# A3.4 — Sleep debt accumulator (7d rolling)
# ────────────────────────────────────────────────────────────────────────────
st.subheader("Sleep debt — 7-day cumulative deficit")
debt_window = nights[-7:]
cumulative = 0.0
debt_xs = []
debt_ys = []
for n in debt_window:
    asleep = n.total_asleep_min or 0
    deficit = max(0, sleep_need_min - asleep)
    cumulative += deficit
    debt_xs.append(n.date)
    debt_ys.append(cumulative)

c1, c2 = st.columns([1, 3])
with c1:
    st.metric("7-day debt", _fmt_hm(cumulative))
with c2:
    if debt_xs:
        fig = go.Figure(go.Scatter(x=debt_xs, y=debt_ys, mode="lines+markers",
                                    line=dict(color=CHART_SERIES[3], width=2),
                                    fill="tozeroy",
                                    fillcolor="rgba(239,154,154,0.15)"))
        fig.update_yaxes(title="Cumulative min deficit")
        apply_theme(fig, height=180)
        st.plotly_chart(fig, use_container_width=True)
explainer_block("sleep_debt_cumulative", chart_data={
    "cumulative_deficit_min": [{"date": str(x), "min": y} for x, y in zip(debt_xs, debt_ys)],
    "need_min": sleep_need_min,
})

st.divider()

# ────────────────────────────────────────────────────────────────────────────
# A3.5 — Sleep stages last night
# ────────────────────────────────────────────────────────────────────────────
st.subheader("Last night — stage breakdown")
stage_total = latest.total_asleep_min or 0
deep = latest.deep_min or 0
rem = latest.rem_min or 0
light = latest.light_min or max(0, stage_total - deep - rem)
awake = latest.awake_min or 0

if stage_total > 0:
    stages = [("Awake", awake, CHART_SERIES[3]),
              ("Light", light, CHART_SERIES[0]),
              ("Deep",  deep,  CHART_SERIES[4]),
              ("REM",   rem,   CHART_SERIES[1])]
    fig = go.Figure()
    for name, mins, color in stages:
        pct = mins / (stage_total + awake) * 100 if (stage_total + awake) else 0
        fig.add_bar(y=["Last night"], x=[mins], orientation="h", name=name,
                    marker_color=color,
                    hovertemplate=f"{name}: {mins:.0f} min ({pct:.1f}%)<extra></extra>")
    fig.update_layout(barmode="stack", showlegend=True)
    apply_theme(fig, height=140)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Deep {deep:.0f} min ({deep/stage_total*100:.1f}%) · "
        f"REM {rem:.0f} min ({rem/stage_total*100:.1f}%) · "
        f"Light {light:.0f} min · Awake {awake:.0f} min"
    )
    explainer_block("sleep_stage_breakdown", chart_data={
        "deep_min": deep, "rem_min": rem, "light_min": light, "awake_min": awake,
        "total_asleep_min": stage_total,
    })


# ────────────────────────────────────────────────────────────────────────────
# Time-range scoped charts
# ────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Trends")
start, end, _ = render_time_range_selector("sleep", default_preset="90d")

nights_df = pd.DataFrame([n.to_dict() for n in nights])
if not nights_df.empty:
    nights_df["date_ts"] = pd.to_datetime(nights_df["date"], errors="coerce")
    win = nights_df[(nights_df["date_ts"] >= start) & (nights_df["date_ts"] <= end)].copy()
else:
    win = pd.DataFrame()

if not win.empty:
    # Stage trends (% of total)
    win["deep_pct"] = win["deep_min"] / win["total_asleep_min"] * 100
    win["rem_pct"] = win["rem_min"]  / win["total_asleep_min"] * 100
    win["light_pct"] = win["light_min"] / win["total_asleep_min"] * 100

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=win["date_ts"], y=win["deep_pct"], mode="lines",
                              name="Deep %",  line=dict(color=CHART_SERIES[4])))
    fig.add_trace(go.Scatter(x=win["date_ts"], y=win["rem_pct"], mode="lines",
                              name="REM %",   line=dict(color=CHART_SERIES[1])))
    fig.add_trace(go.Scatter(x=win["date_ts"], y=win["light_pct"], mode="lines",
                              name="Light %", line=dict(color=CHART_SERIES[0])))
    fig.update_yaxes(title="% of total sleep")
    apply_theme(fig, height=300)
    st.plotly_chart(fig, use_container_width=True)

    # HRV chart with baseline
    if win["hrv_overnight_avg"].notna().any():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=win["date_ts"], y=win["hrv_overnight_avg"],
                                  mode="lines+markers", name="Overnight HRV",
                                  line=dict(color=CHART_SERIES[5])))
        # 7-day rolling
        win_sorted = win.sort_values("date_ts")
        rolling = win_sorted["hrv_overnight_avg"].rolling(7, min_periods=2).mean()
        fig.add_trace(go.Scatter(x=win_sorted["date_ts"], y=rolling,
                                  mode="lines", name="7d avg",
                                  line=dict(color=CHART_SERIES[1], dash="dot")))
        if baseline.get("hrv_baseline"):
            fig.add_hline(y=baseline["hrv_baseline"], line_dash="dash",
                          line_color=COLORS["gold"],
                          annotation_text=f"28d baseline {baseline['hrv_baseline']:.0f}")
        fig.update_yaxes(title="HRV (ms)")
        apply_theme(fig, height=280)
        st.plotly_chart(fig, use_container_width=True)
        explainer_block("hrv_vs_sleep_score", chart_data={
            "points": [
                {"date": str(d), "hrv": (None if pd.isna(h) else float(h))}
                for d, h in zip(win["date_ts"], win["hrv_overnight_avg"])
            ][:120],
        })

    # RHR chart
    if win["resting_hr"].notna().any():
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=win["date_ts"], y=win["resting_hr"],
                                  mode="lines+markers", name="RHR",
                                  line=dict(color=CHART_SERIES[3])))
        if baseline.get("rhr_baseline"):
            fig.add_hline(y=baseline["rhr_baseline"], line_dash="dash",
                          line_color=COLORS["gold"],
                          annotation_text=f"28d baseline {baseline['rhr_baseline']:.0f}")
        fig.update_yaxes(title="Resting HR (bpm)")
        apply_theme(fig, height=240)
        st.plotly_chart(fig, use_container_width=True)
        explainer_block("rhr_vs_sleep_quality", chart_data={
            "points": [
                {"date": str(d), "rhr": (None if pd.isna(r) else float(r))}
                for d, r in zip(win["date_ts"], win["resting_hr"])
            ][:120],
            "baseline_rhr": baseline.get("rhr_baseline"),
        })

    # Consistency scatter — approximate bed time = wake - asleep
    # wearables.csv doesn't have raw bed times; show asleep duration as scatter dots instead.
    fig = go.Figure(go.Scatter(
        x=win["date_ts"], y=win["total_asleep_min"]/60,
        mode="markers", marker=dict(color=CHART_SERIES[0], size=8),
        name="Total asleep (hrs)"))
    fig.add_hline(y=sleep_need_min/60, line_dash="dot",
                  line_color=COLORS["gold"],
                  annotation_text="Need")
    fig.update_yaxes(title="Hours")
    apply_theme(fig, height=220)
    st.plotly_chart(fig, use_container_width=True)
    explainer_block("sleep_consistency", chart_data={
        "asleep_hours": [
            {"date": str(d), "hours": (None if pd.isna(m) else round(float(m) / 60, 2))}
            for d, m in zip(win["date_ts"], win["total_asleep_min"])
        ][:120],
        "need_hours": round(sleep_need_min / 60, 2),
    })


# ────────────────────────────────────────────────────────────────────────────
# A4 — Hypnogram drilldown (expander)
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🛏️ Last night — hypnogram drilldown"):
    if latest and (latest.total_asleep_min or 0) > 0:
        # Apple HealthKit reports stage durations, not minute-level. Generate a
        # representative cyclic pattern (5 cycles per night) so the user can see
        # stage proportions visually — clearly labeled as approximate.
        st.caption(
            "Note: HealthKit reports nightly stage durations rather than "
            "minute-level events. This view shows a representative cycling "
            "pattern based on last night's stage minutes."
        )
        # Build approximate cycles
        try:
            night_start = pd.Timestamp(latest.date) + pd.Timedelta(hours=22)
        except Exception:
            night_start = pd.Timestamp.now().normalize() + pd.Timedelta(hours=22)
        total = latest.total_asleep_min or 0
        n_cycles = 5
        cycle_len = total / n_cycles
        rem_per_cycle  = (latest.rem_min  or 0) / n_cycles
        deep_per_cycle = (latest.deep_min or 0) / n_cycles
        light_per_cycle = max(0, cycle_len - rem_per_cycle - deep_per_cycle)

        # stage order per cycle: light -> deep -> light -> rem
        stage_minutes = []
        time_cursor = night_start
        for _ in range(n_cycles):
            segs = [
                ("Light", light_per_cycle / 2),
                ("Deep",  deep_per_cycle),
                ("Light", light_per_cycle / 2),
                ("REM",   rem_per_cycle),
            ]
            for stage, mins in segs:
                stage_minutes.append((time_cursor, stage, mins))
                time_cursor += pd.Timedelta(minutes=mins)

        # Build step plot
        stage_y = {"Awake": 4, "REM": 3, "Light": 2, "Deep": 1}
        xs, ys = [], []
        for t, stage, mins in stage_minutes:
            xs.append(t)
            ys.append(stage_y[stage])
            xs.append(t + pd.Timedelta(minutes=mins))
            ys.append(stage_y[stage])
        fig = go.Figure(go.Scatter(x=xs, y=ys, mode="lines",
                                    line=dict(color=CHART_SERIES[4], shape="hv", width=3)))
        fig.update_yaxes(
            tickmode="array", tickvals=[1, 2, 3, 4],
            ticktext=["Deep", "Light", "REM", "Awake"],
        )
        apply_theme(fig, height=260)
        st.plotly_chart(fig, use_container_width=True)

        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a: st.metric("Asleep", _fmt_hm(latest.total_asleep_min))
        with col_b: st.metric("Deep",   _fmt_hm(latest.deep_min))
        with col_c: st.metric("REM",    _fmt_hm(latest.rem_min))
        with col_d:
            eff = (latest.total_asleep_min / latest.total_in_bed_min * 100
                   if latest.total_in_bed_min else None)
            st.metric("Efficiency", f"{eff:.0f}%" if eff else "—")

        if latest.hrv_overnight_avg:
            st.caption(f"Overnight HRV (single-night average): {latest.hrv_overnight_avg:.0f} ms")


# ────────────────────────────────────────────────────────────────────────────
# A5 — Wind-down plan + A6 caffeine + A7 smart-alarm window
# ────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Tonight's Wind-down Plan")

# Default target wake = 6:30 AM tomorrow (no gcal connector active)
tomorrow = (datetime.now() + timedelta(days=1)).date()
target_wake = datetime.combine(tomorrow, time(6, 30))
latency_min = 20
target_bed = target_wake - timedelta(minutes=sleep_need_min + latency_min)

st.markdown(
    f"**Lights out by {target_bed.strftime('%-I:%M %p')}** to wake at "
    f"**{target_wake.strftime('%-I:%M %p')}** ready."
)

steps = [
    ("Last caffeine", recommend_cutoff(target_bed, 25.0).strftime("%-I:%M %p")),
    ("Last alcohol (if drinking)", (target_bed - timedelta(hours=4)).strftime("%-I:%M %p")),
    ("Last food / heavy meal", (target_bed - timedelta(hours=3)).strftime("%-I:%M %p")),
    ("Dim lights / glasses on", (target_bed - timedelta(minutes=90)).strftime("%-I:%M %p")),
    ("Stop screens", (target_bed - timedelta(minutes=60)).strftime("%-I:%M %p")),
    ("CJC-1295 + Ipamorelin (empty stomach)", (target_bed - timedelta(minutes=30)).strftime("%-I:%M %p")),
    ("In bed", target_bed.strftime("%-I:%M %p")),
]
for label, when in steps:
    st.markdown(f"- **{when}** — {label}")

# A6 — Caffeine timing
st.divider()
st.subheader("Caffeine Today")
caf_log = load_caffeine_log()
today_log = caf_log[pd.to_datetime(caf_log["timestamp"]).dt.date == datetime.now().date()] if not caf_log.empty else caf_log

caf_cols = st.columns(len(CAFFEINE_PRESETS) + 1)
for col, (label, mg, src) in zip(caf_cols[:-1], CAFFEINE_PRESETS):
    with col:
        if st.button(label, key=f"caf_{src}"):
            log_caffeine(mg, source=src)
            st.cache_data.clear()
            st.rerun()
with caf_cols[-1]:
    custom_mg = st.number_input("Custom mg", min_value=0, max_value=600, value=0, step=5,
                                 key="caf_custom_mg")
    if st.button("Log custom", key="caf_custom_btn") and custom_mg > 0:
        log_caffeine(custom_mg, source="custom")
        st.cache_data.clear()
        st.rerun()

if not today_log.empty:
    last_entry = today_log.sort_values("timestamp").iloc[-1]
    last_ts = pd.Timestamp(last_entry["timestamp"])
    st.info(f"Last caffeine: **{last_ts.strftime('%-I:%M %p')}**, "
            f"**{last_entry['amount_mg']:.0f} mg** ({last_entry['source']})")

    # Decay curve from earliest entry through 18 hrs
    start_curve = pd.Timestamp(today_log["timestamp"].min()).to_pydatetime()
    curve = decay_curve(today_log, start_curve, hours=18)
    residual_at_bed = remaining_mg(today_log, target_bed)
    fig = go.Figure(go.Scatter(x=curve["time"], y=curve["mg_active"],
                                mode="lines", fill="tozeroy",
                                line=dict(color=CHART_SERIES[1])))
    fig.add_vline(x=target_bed, line_dash="dash", line_color=COLORS["gold"],
                  annotation_text=f"Bedtime · {residual_at_bed:.0f} mg active")
    fig.update_yaxes(title="mg active")
    apply_theme(fig, height=240)
    st.plotly_chart(fig, use_container_width=True)
    last_cutoff = recommend_cutoff(target_bed, 25.0)
    st.caption(f"Recommend last caffeine before **{last_cutoff.strftime('%-I:%M %p')}** "
               f"to stay ≤25 mg at bedtime.")
else:
    st.caption("No caffeine logged today. (Default assumption: 2 cups at 8 AM if no entry by 10 AM.)")


# A7 — Smart alarm window
st.divider()
st.subheader("Tomorrow Wake Window")
window_start = (target_wake - timedelta(minutes=18))
window_end = (target_wake + timedelta(minutes=12))
st.markdown(
    f"Set alarm for **{window_start.strftime('%-I:%M %p')}–{window_end.strftime('%-I:%M %p')}** "
    f"(90-min cycle approximation)."
)
st.markdown(f"[Open iOS Clock]({'clock-alarm://'})", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# A8 — Stress-Sleep correlations
# ────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Patterns — sleep vs next-day HRV")

def _pearson(x: pd.Series, y: pd.Series) -> tuple[float, int]:
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < 5:
        return (float("nan"), len(pair))
    a, b = pair.iloc[:, 0], pair.iloc[:, 1]
    if a.std() == 0 or b.std() == 0:
        return (float("nan"), len(pair))
    return (float(a.corr(b)), len(pair))


if not win.empty and "hrv_overnight_avg" in win.columns:
    df = win.sort_values("date_ts").copy()
    df["next_hrv"] = df["hrv_overnight_avg"].shift(-1)

    candidates = {
        "Total asleep min": df["total_asleep_min"],
        "Deep min": df["deep_min"],
        "REM min": df["rem_min"],
        "Deep+REM min": (df["deep_min"].fillna(0) + df["rem_min"].fillna(0)),
    }
    # Add subjective journal joins
    journal = load_journal()
    if not journal.empty:
        journal["d"] = pd.to_datetime(journal["date"], errors="coerce").dt.date
        df["d"] = df["date_ts"].dt.date
        df_j = df.merge(journal[["d", "fatigue_1_5", "mood_1_5", "soreness_1_5"]],
                         on="d", how="left")
        candidates["Subjective fatigue"] = df_j["fatigue_1_5"]

    corr_rows = []
    for label, series in candidates.items():
        r, n_pair = _pearson(series, df["next_hrv"])
        if not np.isnan(r):
            corr_rows.append((label, r, n_pair))

    if corr_rows:
        corr_rows.sort(key=lambda x: abs(x[1]), reverse=True)
        labels = [c[0] for c in corr_rows]
        rs = [c[1] for c in corr_rows]
        colors_for = [CHART_SERIES[2] if r > 0 else CHART_SERIES[3] for r in rs]
        fig = go.Figure(go.Bar(x=rs, y=labels, orientation="h", marker_color=colors_for,
                                text=[f"r={r:.2f} · n={c[2]}" for r, c in zip(rs, corr_rows)],
                                textposition="auto"))
        fig.add_vline(x=0, line_color="#666")
        fig.update_xaxes(range=[-1, 1], title="Pearson r vs next-day HRV")
        apply_theme(fig, height=280)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Correlation ≠ causation. "
                   f"Strongest signal: **{labels[0]}** (r = {rs[0]:.2f}) — worth experimenting with.")


# ────────────────────────────────────────────────────────────────────────────
# A9 — Protocol overlays
# ────────────────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Protocol Correlations")

if not nights_df.empty:
    work = nights_df.copy()
    work["date_ts"] = pd.to_datetime(work["date"], errors="coerce")
    work = work[work["date_ts"] >= start]
    work = work[work["total_asleep_min"].notna() & (work["total_asleep_min"] > 60)]
    if not work.empty:
        # Re-score each night for grouping
        scores = []
        for _, row in work.iterrows():
            n = SleepNight(date=row["date"], total_asleep_min=row["total_asleep_min"],
                            deep_min=row["deep_min"], rem_min=row["rem_min"],
                            hrv_overnight_avg=row["hrv_overnight_avg"])
            scores.append(compute_sleep_score(n, baseline, sleep_need_min)["score"])
        work["score"] = scores

        # TRT injection days = Mon (0), Wed (2), Fri (4) per protocol
        work["dow"] = work["date_ts"].dt.dayofweek
        work["trt_day"] = work["dow"].isin([0, 2, 4])

        col_a, col_b = st.columns(2)
        with col_a:
            grouped = work.groupby("trt_day")["score"].agg(["mean", "count"])
            fig = go.Figure(go.Bar(
                x=["Non-TRT", "TRT day"],
                y=[grouped.loc[False, "mean"] if False in grouped.index else 0,
                   grouped.loc[True, "mean"] if True in grouped.index else 0],
                marker_color=[CHART_SERIES[0], CHART_SERIES[5]],
                text=[f"n={grouped.loc[False, 'count'] if False in grouped.index else 0}",
                      f"n={grouped.loc[True, 'count'] if True in grouped.index else 0}"],
                textposition="outside",
            ))
            fig.update_yaxes(title="Avg sleep score", range=[0, 100])
            fig.update_layout(title="TRT injection days")
            apply_theme(fig, height=260)
            st.plotly_chart(fig, use_container_width=True)
            diff = ((grouped.loc[True, "mean"] if True in grouped.index else 0) -
                    (grouped.loc[False, "mean"] if False in grouped.index else 0))
            st.caption(f"TRT-day score Δ = {diff:+.1f} pts vs non-TRT days.")

        with col_b:
            # Retatrutide: weekly Sunday PM. Group by day-of-week relative to Sun.
            work["days_since_reta"] = (work["dow"] + 1) % 7  # Sun=0
            box = work.groupby("days_since_reta")["score"].mean()
            fig = go.Figure(go.Bar(
                x=[f"Day {i}" for i in box.index],
                y=box.values,
                marker_color=CHART_SERIES[4],
            ))
            fig.update_layout(title="Sleep score by day-from-Reta injection")
            fig.update_yaxes(title="Avg score", range=[0, 100])
            apply_theme(fig, height=260)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(f"Auto-insight: highest score on day "
                       f"{int(box.idxmax())}, lowest day {int(box.idxmin())}.")


# ────────────────────────────────────────────────────────────────────────────
# Sources
# ────────────────────────────────────────────────────────────────────────────
with st.expander("📚 Sources Informing Design"):
    st.markdown(
        """
        - Walker, M. *Why We Sleep* — sleep architecture, learning consolidation, REM/deep roles
        - AASM 2015 — [Recommended Sleep Duration for Healthy Adults](https://aasm.org/clinical-resources/practice-standards/practice-guidelines/)
        - Buchheit, M. (2014) — HRV and training prescription. *Frontiers in Physiology*
        - Stickgold, R. (2013) — Parsing the role of sleep in memory processing. *Current Opinion in Neurobiology*
        - CDC — [How Much Sleep Do I Need?](https://www.cdc.gov/sleep/about_sleep/how_much_sleep.html)
        """
    )
