"""N=1 Experiments — design, track, and evaluate single-subject interventions."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data, write_json
from modules.charts import COLORS, apply_theme, metric_card_html


st.set_page_config(page_title="N=1 Experiments · Protocōl", page_icon="⚗️", layout="wide")

from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("N=1 Experiments")
    st.caption("Single-subject trials · hypothesis → intervention → measurable verdict")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
exps = list(data.nof1_experiments)
bw = data.bloodwork.copy()

# ────────────────────────────────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────────────────────────────────
active = [e for e in exps if e.get("status") == "active"]
complete = [e for e in exps if e.get("status") == "complete"]
beneficial = [e for e in complete if e.get("results", {}).get("verdict") == "likely_beneficial"]
inconclusive = [e for e in complete if e.get("results", {}).get("verdict") == "inconclusive"]

kpis = [
    ("ACTIVE", f"{len(active)}", "currently running", None),
    ("COMPLETE", f"{len(complete)}", "evaluated", None),
    ("BENEFICIAL", f"{len(beneficial)}", "kept in protocol", len(beneficial) > 0),
    ("INCONCLUSIVE", f"{len(inconclusive)}", "no clear signal", None),
    ("TOTAL DESIGNED", f"{len(exps)}", "all-time", None),
    ("WIN RATE", f"{(len(beneficial)/max(len(complete),1))*100:.0f}%", "of completed", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Verdict badge helper
# ────────────────────────────────────────────────────────────────────────────
def verdict_badge(verdict: str) -> str:
    colors = {
        "likely_beneficial": ("#4CAF50", "rgba(76,175,80,0.18)", "✓ Likely Beneficial"),
        "likely_harmful":    ("#F44336", "rgba(244,67,54,0.18)", "✗ Likely Harmful"),
        "inconclusive":      ("#FF9800", "rgba(255,152,0,0.18)", "~ Inconclusive"),
        "neutral":           ("#A0A0A0", "rgba(160,160,160,0.18)", "— No Effect"),
    }
    fg, bg, label = colors.get(verdict, ("#A0A0A0", "rgba(160,160,160,0.18)", verdict or "Pending"))
    return (f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:6px;'
            f'font-size:0.8rem;font-weight:600;">{label}</span>')


def status_badge(status: str) -> str:
    colors = {
        "active":   ("#FFB612", "rgba(255,182,18,0.18)"),
        "complete": ("#4FC3F7", "rgba(79,195,247,0.18)"),
        "planned":  ("#A0A0A0", "rgba(160,160,160,0.18)"),
        "paused":   ("#FF9800", "rgba(255,152,0,0.18)"),
    }
    fg, bg = colors.get(status, ("#A0A0A0", "rgba(160,160,160,0.18)"))
    return (f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;'
            f'font-size:0.72rem;font-weight:600;text-transform:uppercase;">{status}</span>')


# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_active, tab_complete, tab_design, tab_about = st.tabs(
    ["🟡 Active", "✅ Completed", "➕ Design New", "📖 About"]
)

def render_experiment(e: dict) -> None:
    """Render a single experiment card."""
    intervention = e.get("intervention", {})
    outcome = e.get("primary_outcome", {})
    results = e.get("results") or {}

    head_cols = st.columns([5, 1, 1])
    with head_cols[0]:
        st.markdown(f"### {e.get('title', '(untitled)')}")
        st.markdown(f"`{e.get('id', '')}`", help="experiment id")
    with head_cols[1]:
        st.markdown(status_badge(e.get("status", "")), unsafe_allow_html=True)
    with head_cols[2]:
        if results.get("verdict"):
            st.markdown(verdict_badge(results["verdict"]), unsafe_allow_html=True)

    st.markdown(f"**Hypothesis:** {e.get('hypothesis', '—')}")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Intervention**")
        st.markdown(
            f"- **{intervention.get('name', '—')}** ({intervention.get('type', '')})  \n"
            f"- Dose: `{intervention.get('dose', '—')}`  \n"
            f"- Frequency: {intervention.get('frequency', '—')}  \n"
            f"- Window: `{intervention.get('start_date', '—')}` → `{intervention.get('end_date', '—')}`"
        )
    with c2:
        st.markdown("**Primary Outcome**")
        st.markdown(
            f"- Metric: `{outcome.get('metric', '—')}`  \n"
            f"- Source: {outcome.get('source', '—')}  \n"
            f"- Direction: {outcome.get('direction', '—')}  \n"
            f"- Min effect: `{outcome.get('minimum_effect_size', '—')}`"
        )

    secondary = e.get("secondary_outcomes", [])
    if secondary:
        st.markdown(f"**Secondary outcomes:** {', '.join(secondary)}")

    confounders = e.get("confounders_to_control", [])
    if confounders:
        st.markdown(f"**Confounders tracked:** {', '.join(confounders)}")

    # Results
    if results:
        st.markdown("**Results**")
        rc = st.columns(4)
        with rc[0]:
            st.metric("Baseline mean", f"{results.get('baseline_mean', '—')}")
        with rc[1]:
            st.metric("Intervention mean", f"{results.get('intervention_mean', '—')}")
        with rc[2]:
            delta = results.get("delta")
            delta_pct = results.get("delta_pct")
            st.metric("Δ", f"{delta:+.1f}" if isinstance(delta, (int, float)) else "—",
                      f"{delta_pct:+.1f}%" if isinstance(delta_pct, (int, float)) else None)
        with rc[3]:
            d = results.get("cohens_d")
            st.metric("Cohen's d", f"{d:.2f}" if isinstance(d, (int, float)) else "—",
                      results.get("confidence", ""))
        if results.get("notes"):
            st.info(results["notes"])

    # Sources
    sources = e.get("sources_informing_design", [])
    if sources:
        with st.expander(f"📚 Sources informing design ({len(sources)})"):
            for s in sources:
                url = s.get("url", "")
                name = s.get("name", url)
                tier = s.get("tier", "")
                if url:
                    st.markdown(f"- [{name}]({url}) · `{tier}`")
                else:
                    st.markdown(f"- {name} · `{tier}`")

    st.divider()


# ── Active ──────────────────────────────────────────────────────────────────
with tab_active:
    if not active:
        st.info("No active experiments. Design one in the **Design New** tab.")
    else:
        for e in active:
            render_experiment(e)

# ── Completed ───────────────────────────────────────────────────────────────
with tab_complete:
    if not complete:
        st.info("No completed experiments yet.")
    else:
        # Effect-size barchart
        completed_df = pd.DataFrame([
            {
                "title": (e.get("title") or "")[:48],
                "delta_pct": (e.get("results") or {}).get("delta_pct", 0),
                "cohens_d": (e.get("results") or {}).get("cohens_d", 0),
                "verdict": (e.get("results") or {}).get("verdict", "—"),
            }
            for e in complete
        ])
        if not completed_df.empty:
            st.subheader("Effect Sizes — Δ% from baseline")
            fig = go.Figure(go.Bar(
                x=completed_df["delta_pct"], y=completed_df["title"],
                orientation="h",
                marker=dict(color=[COLORS["success"] if v == "likely_beneficial"
                                    else (COLORS["danger"] if v == "likely_harmful"
                                          else COLORS["warning"])
                                    for v in completed_df["verdict"]]),
                text=[f"{d:+.1f}%" for d in completed_df["delta_pct"]],
                textposition="outside",
            ))
            fig.add_vline(x=0, line=dict(color=COLORS["text_muted"], width=1))
            apply_theme(fig, height=max(220, 80 * len(completed_df)))
            fig.update_layout(xaxis=dict(title="Δ% vs baseline"), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        for e in complete:
            render_experiment(e)

# ── Design new ──────────────────────────────────────────────────────────────
with tab_design:
    st.subheader("Design an N=1 Experiment")
    st.caption("Write a falsifiable hypothesis, define one primary outcome, name the confounders.")

    with st.form("new_exp"):
        title = st.text_input("Title", placeholder="e.g. Cold plunge 5x/week — sleep architecture impact")
        hypothesis = st.text_area("Hypothesis", height=80,
                                   placeholder="If I [intervention], then [outcome metric] will [direction] by [effect size] over [duration].")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Intervention**")
            i_name = st.text_input("Name")
            i_type = st.selectbox("Type", ["supplement", "peptide", "hormone", "training", "diet", "behavior", "device"])
            i_dose = st.text_input("Dose")
            i_freq = st.text_input("Frequency")
            i_start = st.date_input("Start date", value=date.today())
            i_end = st.date_input("End date")
        with c2:
            st.markdown("**Primary outcome**")
            o_metric = st.text_input("Metric (e.g. glucose_mg_dl, hrv_sdnn_ms)")
            o_source = st.selectbox("Source", ["bloodwork", "cgm", "wearables", "training", "daily_log", "subjective"])
            o_direction = st.selectbox("Direction", ["decrease", "increase", "no_change"])
            o_min = st.text_input("Min effect size (e.g. 5 mg/dL, 5 ms)")

            st.markdown("**Confounders to track**")
            confounders = st.multiselect(
                "Pick all that apply",
                ["sleep_hrs", "training_load", "stress_notes", "alcohol",
                 "caffeine", "travel", "weight_change", "other_supplements"],
            )

        secondary_str = st.text_input("Secondary outcomes (comma-separated)")

        submit = st.form_submit_button("Save Experiment", use_container_width=True)

    if submit:
        new_id = f"exp_{(len(exps)+1):03d}"
        new_exp = {
            "id": new_id,
            "title": title,
            "hypothesis": hypothesis,
            "intervention": {
                "name": i_name,
                "type": i_type,
                "dose": i_dose,
                "frequency": i_freq,
                "start_date": i_start.isoformat(),
                "end_date": i_end.isoformat(),
            },
            "washout_period_days": 14,
            "primary_outcome": {
                "metric": o_metric,
                "source": o_source,
                "direction": o_direction,
                "minimum_effect_size": o_min,
            },
            "secondary_outcomes": [s.strip() for s in secondary_str.split(",") if s.strip()],
            "confounders_to_control": confounders,
            "blinding": "none",
            "crossover_periods": 0,
            "measurement_frequency": "on_draw",
            "status": "planned",
            "results": None,
            "sources_informing_design": [],
            "created_date": date.today().isoformat(),
            "last_updated": date.today().isoformat(),
        }
        exps.append(new_exp)
        write_json("nof1_experiments.json", exps)
        st.success(f"Experiment {new_id} saved.")
        st.rerun()

# ── About ───────────────────────────────────────────────────────────────────
with tab_about:
    st.markdown("""
### What Makes a Good N=1 Experiment

The trap with personal optimization is "I started X, I feel better, X works."
Without a hypothesis-driven structure, you've just stacked confirmation bias.

**Five non-negotiables:**

1. **One primary outcome.** Numeric, measurable, pre-specified. No fishing.
2. **A baseline window.** At least 2 measurements before the intervention starts.
3. **A minimum effect size.** Decided in advance — keeps you from over-fitting noise.
4. **Tracked confounders.** Sleep, training load, stress, alcohol — all the things that move the outcome too.
5. **A washout when reasonable.** Long enough to see the metric drift back, ~2-4 wks for most supplements.

### Effect Size Heuristics

| Cohen's d | Read |
|---|---|
| < 0.2 | Trivial / lost in noise |
| 0.2 – 0.5 | Small but real |
| 0.5 – 0.8 | Moderate — worth keeping |
| > 0.8 | Large — confident keeper |

### Crossover Design

If feasible, run on → washout → off → washout → on. This is the cleanest single-subject design — your own metabolism is the control.
""")
