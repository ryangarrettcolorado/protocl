"""Overview — at-a-glance state of the system.

Answers in <5 seconds: How am I doing? What changed? What needs attention?
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import (
    load_data,
    refresh_data,
    latest_bloodwork_draw,
    previous_bloodwork_draw,
)
from modules.charts import (
    COLORS,
    apply_theme,
    metric_card_html,
    status_label,
)
from modules.reference_ranges import load_reference
from modules.biomarker_aliases import display_name


st.set_page_config(page_title="Overview · Protocōl", page_icon="⚗️", layout="wide")



from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Overview")
    st.caption("How am I doing right now · what changed recently · what needs attention")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()


data = load_data()
ref = load_reference()


# ────────────────────────────────────────────────────────────────────────────
# KPI row — composite health metrics
# ────────────────────────────────────────────────────────────────────────────

def calc_health_score() -> tuple[int, dict]:
    """Composite 0-100 weighted health score with component breakdown."""
    components = {}

    # Bloodwork: % of tracked biomarkers in optimal range (35%)
    latest = latest_bloodwork_draw(data.bloodwork)
    if not latest.empty:
        tracked = 0
        in_optimal = 0
        for _, row in latest.iterrows():
            r = ref.get(row["biomarker_canonical"])
            if r is None or "optimal_low" not in r:
                continue
            tracked += 1
            if r["optimal_low"] <= row["value"] <= r["optimal_high"]:
                in_optimal += 1
        components["bloodwork"] = (in_optimal / tracked * 100) if tracked else 50
    else:
        components["bloodwork"] = 50

    # Metabolic: TIR proxy from CGM (20%)
    if not data.cgm_readings.empty:
        recent = data.cgm_readings.tail(2016)  # ~7 days at 5min intervals
        in_range = ((recent["glucose_mg_dl"] >= 70) & (recent["glucose_mg_dl"] <= 140)).mean()
        components["metabolic"] = in_range * 100
    else:
        components["metabolic"] = 50

    # Recovery: 7-day HRV vs 30-day baseline (20%)
    if not data.wearables.empty:
        w = data.wearables.sort_values("date")
        recent_hrv = w["hrv_sdnn_ms"].tail(7).mean()
        baseline_hrv = w["hrv_sdnn_ms"].mean()
        ratio = recent_hrv / baseline_hrv if baseline_hrv > 0 else 1.0
        components["recovery"] = min(100, max(0, 50 + (ratio - 1) * 200))
    else:
        components["recovery"] = 50

    # Body comp: trajectory of body fat % (15%)
    if not data.inbody.empty and len(data.inbody) >= 2:
        ib = data.inbody.sort_values("date")
        delta_bf = ib["body_fat_pct"].iloc[-1] - ib["body_fat_pct"].iloc[0]
        # Progress toward improvement
        components["body_comp"] = 50 + min(50, max(-50, -delta_bf * 5))
    else:
        components["body_comp"] = 50

    # Training: Zone 2 minutes / week vs 150-min target (10%)
    if not data.training.empty:
        recent_week = data.training[data.training["date"] >= (pd.Timestamp("2026-05-25") - pd.Timedelta(days=7))]
        z2 = recent_week["zone2_min"].sum() if "zone2_min" in recent_week else 0
        components["training"] = min(100, z2 / 150 * 100)
    else:
        components["training"] = 50

    weights = {"bloodwork": 0.35, "metabolic": 0.20, "recovery": 0.20, "body_comp": 0.15, "training": 0.10}
    score = sum(components[k] * weights[k] for k in components)
    return int(round(score)), components


score, components = calc_health_score()

# Protocol adherence
active_protocol = data.protocol[data.protocol["end_date"].isna()] if not data.protocol.empty else pd.DataFrame()
adherence = active_protocol["adherence_pct"].mean() if not active_protocol.empty else 0

# Recovery score
recovery_score = components.get("recovery", 50)

# Body comp delta (30d lean mass)
ib = data.inbody.sort_values("date") if not data.inbody.empty else pd.DataFrame()
if len(ib) >= 2:
    cutoff = pd.Timestamp("2026-05-25") - pd.Timedelta(days=30)
    recent = ib[ib["date"] >= cutoff]
    if len(recent) >= 2:
        lean_delta = recent["lean_mass_lbs"].iloc[-1] - recent["lean_mass_lbs"].iloc[0]
    else:
        lean_delta = ib["lean_mass_lbs"].iloc[-1] - ib["lean_mass_lbs"].iloc[-2]
else:
    lean_delta = 0.0

# Open risks
risk_count = _calc_risks = 0
latest = latest_bloodwork_draw(data.bloodwork)
if not latest.empty:
    for _, row in latest.iterrows():
        r = ref.get(row["biomarker_canonical"])
        if r is None:
            continue
        s = status_label(row["value"], r.get("optimal_low"), r.get("optimal_high"),
                         r.get("lab_low"), r.get("lab_high"))
        if s == "Risk":
            risk_count += 1

# Open action items
open_actions = data.action_items[data.action_items["status"].isin(["open", "in_progress"])] if not data.action_items.empty else pd.DataFrame()
open_high = len(open_actions[open_actions["priority"] == "high"]) if not open_actions.empty else 0


k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
with k1:
    st.markdown(metric_card_html("Health Score", f"{score}", "of 100"), unsafe_allow_html=True)
with k2:
    # Biological age delta — placeholder until biological_age module ships
    st.markdown(metric_card_html("Bio Age Δ", "−2.1y", "vs chronological", True), unsafe_allow_html=True)
with k3:
    st.markdown(metric_card_html("Adherence", f"{int(adherence)}%", "active protocol"), unsafe_allow_html=True)
with k4:
    st.markdown(metric_card_html("Recovery", f"{int(recovery_score)}", "7d vs baseline"), unsafe_allow_html=True)
with k5:
    sign = "+" if lean_delta >= 0 else ""
    st.markdown(metric_card_html("Lean Mass 30d", f"{sign}{lean_delta:.1f} lb",
                                  "tracking up" if lean_delta > 0 else "tracking down",
                                  lean_delta >= 0), unsafe_allow_html=True)
with k6:
    st.markdown(metric_card_html("Open Risks", f"{risk_count}", "out-of-range"), unsafe_allow_html=True)
with k7:
    st.markdown(metric_card_html("Action Items", f"{len(open_actions)}", f"{open_high} high"), unsafe_allow_html=True)


st.markdown("")


# ────────────────────────────────────────────────────────────────────────────
# Row 2 — Longitudinal biomarker trend with protocol overlays
# ────────────────────────────────────────────────────────────────────────────

st.subheader("Protocol Timeline · Key Biomarker Trends")

if not data.bloodwork.empty:
    # Pick 3 high-signal biomarkers
    featured = ["testosterone_total_ng_dl", "hscrp_mg_l", "homa_ir"]
    fig = go.Figure()
    bw = data.bloodwork.sort_values("date")

    for i, bm in enumerate(featured):
        sub = bw[bw["biomarker_canonical"] == bm]
        if sub.empty:
            continue
        # Normalize to relative scale so they fit on one chart (0-100 of optimal high)
        r = ref.get(bm, {})
        target = r.get("optimal_high", 1)
        normalized = sub["value"] / target * 100
        fig.add_trace(go.Scatter(
            x=sub["date"], y=normalized,
            mode="lines+markers",
            name=display_name(bm),
            line=dict(color=COLORS["chart_series"][i], width=2.5),
            marker=dict(size=8),
            hovertemplate=f"<b>{display_name(bm)}</b><br>%{{x|%b %Y}}<br>%{{customdata}}<extra></extra>",
            customdata=sub["value"].astype(str) + " " + sub["unit"],
        ))

    # Protocol start markers
    for _, item in active_protocol.head(8).iterrows():
        try:
            fig.add_vline(
                x=item["start_date"],
                line=dict(color=COLORS["text_faint"], width=1, dash="dot"),
                annotation_text=item["name"][:18],
                annotation_position="top",
                annotation_font_size=9,
                annotation_font_color=COLORS["text_muted"],
            )
        except Exception:
            continue

    apply_theme(fig, height=380)
    fig.update_layout(
        yaxis_title="% of optimal target",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No bloodwork data yet — add a draw on the Bloodwork page or use the Import Center.")


# ────────────────────────────────────────────────────────────────────────────
# Row 3 — Risk flags · Active experiments
# ────────────────────────────────────────────────────────────────────────────

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("⚠️ Top Risk Flags")
    flags = []
    latest = latest_bloodwork_draw(data.bloodwork)
    prev = previous_bloodwork_draw(data.bloodwork)
    if not latest.empty:
        for _, row in latest.iterrows():
            r = ref.get(row["biomarker_canonical"])
            if r is None:
                continue
            s = status_label(row["value"], r.get("optimal_low"), r.get("optimal_high"),
                             r.get("lab_low"), r.get("lab_high"))
            if s in ("Risk", "Monitor"):
                prev_val = None
                if not prev.empty:
                    pr = prev[prev["biomarker_canonical"] == row["biomarker_canonical"]]
                    if not pr.empty:
                        prev_val = pr["value"].iloc[0]
                flags.append({
                    "name": display_name(row["biomarker_canonical"]),
                    "value": row["value"],
                    "unit": row["unit"],
                    "status": s,
                    "prev": prev_val,
                    "optimal_low": r.get("optimal_low"),
                    "optimal_high": r.get("optimal_high"),
                })

    # Sort: Risk first
    flags.sort(key=lambda f: 0 if f["status"] == "Risk" else 1)

    if not flags:
        st.success("No active risk flags. All tracked biomarkers within range.")
    else:
        for f in flags[:5]:
            color_cls = "risk-card" if f["status"] == "Monitor" else "risk-card"
            border = "#F44336" if f["status"] == "Risk" else "#FF9800"
            delta_html = ""
            if f["prev"] is not None:
                d = f["value"] - f["prev"]
                arrow = "↑" if d > 0 else "↓"
                delta_html = f'<span style="color:{COLORS["text_muted"]}; font-size:0.85rem">{arrow} {abs(d):.1f} vs last draw</span>'
            st.markdown(
                f'<div class="risk-card" style="border-left-color:{border}">'
                f'<div style="display:flex;justify-content:space-between;align-items:center">'
                f'<span style="font-weight:600">{f["name"]}</span>'
                f'<span class="badge-{f["status"].lower()}">{f["status"]}</span>'
                f'</div>'
                f'<div style="margin-top:4px;color:{COLORS["text_primary"]};font-size:1.1rem">'
                f'{f["value"]} {f["unit"]} '
                f'<span style="color:{COLORS["text_muted"]};font-size:0.85rem">'
                f'(optimal {f["optimal_low"]}–{f["optimal_high"]})</span></div>'
                f'<div style="margin-top:2px">{delta_html}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

with col_right:
    st.subheader("🧪 Active N=1 Experiments")
    active_exps = [e for e in data.nof1_experiments if e.get("status") == "active"]
    completed = [e for e in data.nof1_experiments if e.get("status") == "complete"]

    if not active_exps and not completed:
        st.info("No experiments yet — design one on the N=1 Experiments page.")
    else:
        for exp in active_exps[:3]:
            iv = exp.get("intervention", {})
            st.markdown(
                f'<div class="rec-card">'
                f'<div class="rec-card-title">🔬 {exp["title"]}</div>'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem">'
                f'Intervention: {iv.get("name", "—")} · {iv.get("dose", "")} · {iv.get("frequency", "")}'
                f'</div>'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.8rem;margin-top:4px">'
                f'Status: <span style="color:{COLORS["gold"]}">{exp["status"].upper()}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        for exp in completed[:2]:
            v = exp.get("results", {}).get("verdict", "inconclusive")
            verdict_color = {
                "likely_beneficial": COLORS["success"],
                "likely_neutral": COLORS["text_muted"],
                "likely_harmful": COLORS["danger"],
                "inconclusive": COLORS["warning"],
            }.get(v, COLORS["text_muted"])
            st.markdown(
                f'<div class="rec-card" style="opacity:0.85">'
                f'<div class="rec-card-title" style="color:{COLORS["text_primary"]}">✓ {exp["title"]}</div>'
                f'<div style="color:{verdict_color};font-size:0.85rem;font-weight:600">'
                f'Verdict: {v.replace("_", " ").title()}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────────────
# Row 4 — Top recommendations
# ────────────────────────────────────────────────────────────────────────────

st.subheader("🎯 Top Recommendations")

# Phase-1 deterministic recommendations (LLM narrative layer ships in Session 3)
recommendations = []
if not latest.empty:
    # Hematocrit watch
    hct = latest[latest["biomarker_canonical"] == "hematocrit_pct"]
    if not hct.empty and hct["value"].iloc[0] > 48:
        recommendations.append({
            "title": "Monitor hematocrit on TRT",
            "evidence": f"HCT at {hct['value'].iloc[0]:.1f}% — trending up. Above 52% indicates polycythemia risk.",
            "actions": ["Donate blood every 8-12 weeks", "Stay well hydrated before draws", "Re-test in 6 weeks"],
            "source_name": "Defy Medical TRT protocols",
            "source_url": "https://www.defymedical.com",
            "tier": "T3",
            "priority": "high",
        })

    # Vitamin D
    vd = latest[latest["biomarker_canonical"] == "vitamin_d_ng_ml"]
    if not vd.empty and vd["value"].iloc[0] < 60:
        recommendations.append({
            "title": "Push Vitamin D into 60-80 ng/mL window",
            "evidence": f"Vitamin D at {vd['value'].iloc[0]:.0f} ng/mL — below optimal threshold.",
            "actions": ["Continue D3 5000 IU + K2 200mcg", "Get 15-20 min midday sun when possible", "Recheck at next draw"],
            "source_name": "GrassrootsHealth",
            "source_url": "https://www.grassrootshealth.net",
            "tier": "T2",
            "priority": "medium",
        })

# Zone 2 recommendation if weekly total is low
if not data.training.empty:
    recent_week = data.training[data.training["date"] >= (pd.Timestamp("2026-05-25") - pd.Timedelta(days=7))]
    z2 = recent_week["zone2_min"].sum() if "zone2_min" in recent_week else 0
    if z2 < 150:
        recommendations.append({
            "title": "Add Zone 2 minutes to hit 150/week",
            "evidence": f"This week: {int(z2)} Zone 2 min. Target 150+ for mitochondrial adaptation.",
            "actions": ["Add a 60-min easy ride mid-week", "Use HR cap of 124 bpm", "Track via Strava → Training page"],
            "source_name": "Dr. Iñigo San Millán / Dr. Peter Attia",
            "source_url": "https://peterattiamd.com/category/exercise/",
            "tier": "T3",
            "priority": "medium",
        })

if not recommendations:
    st.success("No high-priority recommendations active. Your data is on-trend.")
else:
    cols = st.columns(min(3, len(recommendations)))
    for i, rec in enumerate(recommendations[:3]):
        with cols[i]:
            tier_cls = f"tier-{rec['tier'].lower()}"
            pri_color = {"high": COLORS["danger"], "medium": COLORS["warning"], "low": COLORS["text_muted"]}[rec["priority"]]
            actions_html = "".join([f"<li>{a}</li>" for a in rec["actions"]])
            st.markdown(
                f'<div class="rec-card">'
                f'<div class="rec-card-title">{rec["title"]}</div>'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem;margin-bottom:6px">'
                f'{rec["evidence"]}</div>'
                f'<ul style="color:{COLORS["text_primary"]};font-size:0.85rem;margin:6px 0;padding-left:18px">{actions_html}</ul>'
                f'<div style="margin-top:8px;font-size:0.78rem">'
                f'<a href="{rec["source_url"]}" target="_blank" style="color:{COLORS["text_muted"]};text-decoration:none">{rec["source_name"]}</a> · '
                f'<span class="{tier_cls}">Tier {rec["tier"][-1]}</span> · '
                f'<span style="color:{pri_color};font-weight:600">{rec["priority"].upper()}</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ────────────────────────────────────────────────────────────────────────────
# Row 5 — High-priority action items
# ────────────────────────────────────────────────────────────────────────────

st.subheader("✅ Action Items")

if open_actions.empty:
    st.info("No open action items.")
else:
    pri_order = {"high": 0, "medium": 1, "low": 2}
    open_sorted = open_actions.copy()
    open_sorted["pri_order"] = open_sorted["priority"].map(pri_order)
    open_sorted = open_sorted.sort_values(["pri_order", "due_date"]).head(5)

    for _, row in open_sorted.iterrows():
        pri_color = {"high": COLORS["danger"], "medium": COLORS["warning"], "low": COLORS["text_muted"]}[row["priority"]]
        due = row["due_date"].strftime("%b %d") if pd.notna(row["due_date"]) else "—"
        st.markdown(
            f'<div class="risk-card" style="border-left-color:{pri_color}">'
            f'<div style="display:flex;justify-content:space-between">'
            f'<div>'
            f'<span style="font-weight:600">{row["title"]}</span>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem;margin-top:4px">{row["why_it_matters"]}</div>'
            f'</div>'
            f'<div style="text-align:right">'
            f'<span style="color:{pri_color};font-weight:600;font-size:0.78rem">{row["priority"].upper()}</span>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.78rem;margin-top:2px">Due {due}</div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )


# ────────────────────────────────────────────────────────────────────────────
# Row 6 — Symptom check-in (collapsible)
# ────────────────────────────────────────────────────────────────────────────

with st.expander("📋 Daily symptom check-in"):
    with st.form("symptom_checkin", clear_on_submit=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1: energy = st.slider("Energy", 1, 10, 7)
        with c2: mood = st.slider("Mood", 1, 10, 7)
        with c3: libido = st.slider("Libido", 1, 10, 7)
        with c4: recovery = st.slider("Recovery", 1, 10, 7)
        with c5: stress = st.slider("Stress", 1, 10, 4)
        notes = st.text_input("Notes (optional)")
        submitted = st.form_submit_button("Save check-in")
        if submitted:
            from modules.data_loader import append_row
            today = datetime(2026, 5, 25).strftime("%Y-%m-%d")
            append_row("context_notes.csv", {
                "date": today, "category": "checkin",
                "note": f"E:{energy} M:{mood} L:{libido} R:{recovery} S:{stress} | {notes}",
            })
            st.success("Saved.")
