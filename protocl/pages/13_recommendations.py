"""Recommendations — rule-based + LLM-augmented next-best-actions."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from modules.data_loader import load_data, refresh_data, latest_bloodwork_draw, append_row
from modules.charts import COLORS, metric_card_html
from modules.reference_ranges import load_reference
from modules.biomarker_aliases import display_name
from modules.llm import llm_chat, llm_badge, is_configured


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Recommendations")
    st.caption("Rule-based next-best-actions + optional LLM rationale")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

st.markdown(f"**LLM Status:** {llm_badge()}", unsafe_allow_html=True)

data = load_data()
bw = data.bloodwork.copy()
ref = load_reference()
protocol = data.protocol.copy()
wearables = data.wearables.copy()
training = data.training.copy()
inbody = data.inbody.copy()
daily_log = data.daily_log.copy()
action_items = data.action_items.copy()

# ────────────────────────────────────────────────────────────────────────────
# Rule-based recommendation engine
# ────────────────────────────────────────────────────────────────────────────
TODAY = pd.Timestamp("2026-05-25")
recs = []  # each: {priority, category, title, why, evidence, action}

# 1. Bloodwork-driven
latest_bw = latest_bloodwork_draw(bw)
if not latest_bw.empty:
    for _, row in latest_bw.iterrows():
        canonical = row["biomarker_canonical"]
        r = ref.get(canonical)
        if not r:
            continue
        val = row["value"]
        opt_low, opt_high = r.get("optimal_low"), r.get("optimal_high")
        lab_low, lab_high = r.get("lab_low"), r.get("lab_high")

        # High-priority recommendations only fire on selected markers
        if canonical == "hematocrit_pct" and val > 50:
            recs.append({
                "priority": "high" if val > 52 else "medium",
                "category": "protocol",
                "title": f"Watch hematocrit on TRT ({val:.1f}%)",
                "why": "Polycythemia is the most common TRT side effect. >52% raises stroke risk.",
                "evidence": f"Current HCT {val:.1f}%, lab cutoff ~{lab_high}%.",
                "action": "Donate whole blood; recheck CBC in 6–8 weeks.",
                "related": "hematocrit_pct",
            })
        elif canonical == "hscrp_mg_l" and val > 1.0:
            recs.append({
                "priority": "high" if val > 3.0 else "medium",
                "category": "inflammation",
                "title": f"Reduce systemic inflammation (hsCRP {val:.2f} mg/L)",
                "why": "hsCRP is one of the strongest cardiovascular event predictors. Optimal target <0.8 mg/L.",
                "evidence": f"hsCRP {val:.2f} mg/L > optimal {opt_high}.",
                "action": "Audit sleep, alcohol, omega-3 index, dental health. Re-draw with the next CBC.",
                "related": "hscrp_mg_l",
            })
        elif canonical == "apob_mg_dl" and opt_high and val > opt_high:
            recs.append({
                "priority": "high",
                "category": "cardiovascular",
                "title": f"ApoB above target ({val:.0f} mg/dL)",
                "why": "ApoB is the strongest single lipid risk marker — count of atherogenic particles.",
                "evidence": f"ApoB {val:.0f} > optimal {opt_high}.",
                "action": "Discuss statin/PCSK9 with prescriber. Reduce sat fat; up fiber to 35g+/day.",
                "related": "apob_mg_dl",
            })
        elif canonical == "ferritin_ng_ml" and opt_low and val < opt_low:
            recs.append({
                "priority": "low",
                "category": "nutrition",
                "title": f"Ferritin trending low ({val:.0f} ng/mL)",
                "why": "Low ferritin impairs oxygen carrying and endurance performance.",
                "evidence": f"Ferritin {val:.0f} < optimal {opt_low}.",
                "action": "Add red meat 2x/wk or iron bisglycinate with vit C.",
                "related": "ferritin_ng_ml",
            })
        elif canonical == "vitamin_d_25oh_ng_ml" and opt_low and val < opt_low:
            recs.append({
                "priority": "medium",
                "category": "supplement",
                "title": f"Vitamin D below optimal ({val:.0f} ng/mL)",
                "why": "Vit D 25(OH) optimal 50–80 ng/mL per GrassrootsHealth; below 30 = clinically deficient.",
                "evidence": f"25(OH)D {val:.0f} < optimal {opt_low}.",
                "action": "5000 IU D3 + 100 mcg K2 daily; recheck in 90 days.",
                "related": "vitamin_d_25oh_ng_ml",
            })

# 2. Training-driven
if not training.empty:
    last_7 = training[training["date"] >= TODAY - pd.Timedelta(days=7)]
    z2_7d = last_7["zone2_min"].sum()
    if z2_7d < 180:
        recs.append({
            "priority": "medium",
            "category": "training",
            "title": f"Zone-2 dose below target ({int(z2_7d)} min last 7d)",
            "why": "Attia minimum 180 min/wk — mitochondrial density depends on the volume of low-intensity work.",
            "evidence": f"Last 7d Z2: {int(z2_7d)} min, target ≥180.",
            "action": "Add one 60-min ride at nose-breathing pace this week.",
            "related": "zone2_min",
        })

# 3. Wearable-driven
if not wearables.empty:
    w = wearables.sort_values("date")
    w7 = w.tail(7)
    sleep_avg = w7["sleep_duration_hrs"].mean()
    if sleep_avg < 7.0:
        recs.append({
            "priority": "high",
            "category": "sleep",
            "title": f"Sleep duration below 7h ({sleep_avg:.1f}h avg)",
            "why": "Chronic <7h sleep collapses HRV, glucose handling, and recovery in days.",
            "evidence": f"7d sleep avg {sleep_avg:.1f} h.",
            "action": "Hard wind-down by 21:30; remove evening alcohol; magnesium glycinate.",
            "related": "sleep_duration_hrs",
        })

# 4. Body comp-driven
if not inbody.empty and len(inbody) >= 2:
    inb = inbody.sort_values("date")
    smm_delta = inb["skeletal_muscle_mass_lbs"].iloc[-1] - inb["skeletal_muscle_mass_lbs"].iloc[-2]
    if smm_delta < -0.5:
        recs.append({
            "priority": "medium",
            "category": "training",
            "title": f"Lean mass declining ({smm_delta:+.1f} lb last scan)",
            "why": "Lean loss compounds — protect it during any caloric deficit.",
            "evidence": f"SMM {inb['skeletal_muscle_mass_lbs'].iloc[-2]:.1f} → {inb['skeletal_muscle_mass_lbs'].iloc[-1]:.1f}.",
            "action": "Push protein to 1g/lb lean; 3+ resistance sessions/wk.",
            "related": "skeletal_muscle_mass_lbs",
        })

# Sort by priority
priority_order = {"high": 0, "medium": 1, "low": 2}
recs.sort(key=lambda x: priority_order.get(x["priority"], 3))

# ────────────────────────────────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────────────────────────────────
high = [r for r in recs if r["priority"] == "high"]
medium = [r for r in recs if r["priority"] == "medium"]
low = [r for r in recs if r["priority"] == "low"]

kpis = [
    ("TOTAL RECS", f"{len(recs)}", "active", None),
    ("HIGH", f"{len(high)}", "act this week", len(high) == 0),
    ("MEDIUM", f"{len(medium)}", "act this month", None),
    ("LOW", f"{len(low)}", "watchful", None),
    ("CATEGORIES", f"{len(set(r['category'] for r in recs))}", "domains touched", None),
    ("LLM MODE", "LIVE" if is_configured() else "DEMO", "API status",
     is_configured()),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_recs, tab_llm = grouped_sections(["✅ Recommendations", "🤖 LLM Reasoning"])

# ── Recs ────────────────────────────────────────────────────────────────────
with tab_recs:
    if not recs:
        st.success("No recommendations active. System is in a clean state.")
    else:
        for r in recs:
            priority_color = {"high": COLORS["danger"], "medium": COLORS["warning"],
                              "low": COLORS["chart_series"][1]}[r["priority"]]
            with st.container():
                head_cols = st.columns([5, 1, 1])
                with head_cols[0]:
                    st.markdown(f"### {r['title']}")
                    st.caption(f"Category: **{r['category']}** · Related metric: `{r.get('related', '—')}`")
                with head_cols[1]:
                    st.markdown(
                        f'<div style="background:{priority_color}22;color:{priority_color};'
                        f'padding:5px 10px;border-radius:6px;text-align:center;'
                        f'font-weight:600;font-size:0.75rem;">{r["priority"].upper()}</div>',
                        unsafe_allow_html=True,
                    )
                with head_cols[2]:
                    if st.button("➕ Action Item", key=f"add_{r['title'][:20]}", use_container_width=True):
                        append_row("action_items.csv", {
                            "id": f"act_{len(action_items)+1:03d}",
                            "title": r["title"],
                            "priority": r["priority"],
                            "category": r["category"],
                            "why_it_matters": r["why"],
                            "due_date": (TODAY + pd.Timedelta(days=14)).date().isoformat(),
                            "related_metrics": r.get("related", ""),
                            "status": "open",
                            "source": "auto_recommendation",
                            "created_date": TODAY.date().isoformat(),
                        })
                        st.success(f"Added to action items.")

                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**Why it matters**  \n{r['why']}")
                    st.markdown(f"**Evidence**  \n{r['evidence']}")
                with c2:
                    st.markdown(f"**Recommended action**  \n{r['action']}")
                st.divider()

# ── LLM ─────────────────────────────────────────────────────────────────────
with tab_llm:
    st.subheader("LLM Reasoning Over Your Recommendations")
    st.caption("The LLM gets the full rec list + your latest snapshot and writes a prioritized briefing.")

    if not is_configured():
        st.warning(
            "LLM not configured. To enable: drop your OpenAI key into "
            "`.streamlit/secrets.toml` as `OPENAI_API_KEY = \"sk-...\"`. "
            "In demo mode, the rule-based recs above are the source of truth."
        )

    if st.button("🤖 Generate weekly briefing", use_container_width=True):
        # Build snapshot for the LLM
        snapshot = {
            "today": TODAY.strftime("%Y-%m-%d"),
            "recommendations": recs,
            "latest_bloodwork": latest_bw[["biomarker_canonical", "value", "unit"]].to_dict(orient="records"),
            "recent_7d_sleep_hrs": wearables.tail(7)["sleep_duration_hrs"].mean() if not wearables.empty else None,
            "recent_7d_z2_min": training.tail(7)["zone2_min"].sum() if not training.empty else None,
            "current_protocol_count": len(protocol[protocol["status"] == "active"]) if "status" in protocol.columns else len(protocol),
        }
        prompt = (
            "Below is a Protocōl health-OS snapshot with a rule-based recommendation list. "
            "Write a tight 200-word weekly briefing. Prioritize the highest-leverage actions. "
            "Reference specific numbers from the snapshot. End with one sentence — the single "
            "most important action for the next 7 days.\n\n"
            f"```json\n{json.dumps(snapshot, default=str, indent=2)[:4000]}\n```"
        )
        with st.spinner("Reasoning..."):
            briefing = llm_chat(prompt, max_tokens=600)
        st.markdown("### Weekly Briefing")
        st.markdown(briefing)
