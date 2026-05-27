"""Biological Age — Levine PhenoAge with biomarker contribution breakdown."""
from __future__ import annotations

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data
from modules.charts import COLORS, apply_theme, metric_card_html
from modules.bioage import (
    compute_phenoage,
    phenoage_over_time,
    latest_phenoage,
    COEFFS,
)


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Biological Age")
    st.caption("Levine 2018 PhenoAge — 9 clinical biomarkers + chronological age")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
bw = data.bloodwork.copy()

BIRTH_DATE = pd.Timestamp("1983-11-14")  # from user_background

if bw.empty:
    st.info("No bloodwork loaded yet — PhenoAge needs all 9 biomarkers.")
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# Compute PhenoAge series
# ────────────────────────────────────────────────────────────────────────────
series = phenoage_over_time(bw, BIRTH_DATE)
latest = latest_phenoage(bw, BIRTH_DATE)

if not latest or not latest.ok:
    if latest:
        st.error(f"Latest draw missing required biomarkers: {', '.join(latest.missing_inputs)}")
    else:
        st.error("Unable to compute PhenoAge from current data.")
    st.stop()

first = series.iloc[0]
last = series.iloc[-1]
delta_first_last = last["pheno_age"] - first["pheno_age"]
chrono_delta = last["chronological_age"] - first["chronological_age"]
trajectory = delta_first_last - chrono_delta  # bio-age delta net of time passing

# ────────────────────────────────────────────────────────────────────────────
# KPI Cards
# ────────────────────────────────────────────────────────────────────────────
kpis = [
    ("PHENO AGE", f"{last['pheno_age']:.1f} y",
     f"{last['delta']:+.1f}y vs chronological", last["delta"] < 0),
    ("CHRONOLOGICAL", f"{last['chronological_age']:.1f} y", "actual age", None),
    ("Δ FROM FIRST DRAW", f"{delta_first_last:+.1f} y",
     f"vs +{chrono_delta:.1f}y wall-clock", trajectory < 0),
    ("AGING RATE", f"{trajectory/chrono_delta if chrono_delta else 0:+.2f}",
     "biological yr per calendar yr", trajectory / chrono_delta < 1 if chrono_delta else False),
    ("10-YR MORTALITY", f"{last['mortality_score']*100:.2f}%",
     "PhenoAge Gompertz estimate", last["mortality_score"] < 0.05),
    ("DRAWS", f"{len(series)}", "compute history", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

with st.expander("📖 How this number is calculated — Levine PhenoAge methodology",
                 expanded=False):
    st.markdown("""
**PhenoAge (Levine et al., 2018)** estimates biological age from a weighted
combination of **9 routine clinical biomarkers** + chronological age:

| Biomarker | Role |
|---|---|
| Albumin (g/dL) | Liver function, nutritional status |
| Creatinine (mg/dL) | Kidney function |
| Glucose (mg/dL) | Metabolic / insulin resistance |
| C-reactive protein (mg/L) | Systemic inflammation |
| Lymphocyte % | Immune profile |
| Mean cell volume (fL) | Red-cell maturity |
| Red cell distribution width (%) | Heterogeneity of RBC size |
| Alkaline phosphatase (U/L) | Hepatic / bone turnover |
| White blood cell count (10³/μL) | Immune activation |

**The math:** each biomarker is multiplied by a coefficient fit to NHANES III
mortality data. The weighted sum (`xb`) is converted to a 10-year mortality
score via a Gompertz model, then transformed back into a "biological age in
years" that matches the chronological age of someone with the same mortality
risk in the reference population.

**Why use it?** Of the validated bio-age scores (PhenoAge, GrimAge, DunedinPACE),
PhenoAge is the only one that runs from a standard blood panel — no methylation
chip required. It tracks all-cause mortality risk better than chronological age
in independent cohorts.

**How to read it.**
- **Delta < 0** = you're biologically younger than the calendar. Good.
- **Delta > 0** = your blood signature is closer to an older population's average.
- A single point is noise; the **trajectory over time** is the signal.

**Caveats.** PhenoAge was trained on a US population sample and may be less
accurate for younger / very fit individuals. It's a screening number, not a
diagnostic. Acute illness or recent training stress can move CRP, WBC, and
glucose enough to wobble the score by ±2 years.
    """)

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_trend, tab_breakdown, tab_levers, tab_about = grouped_sections(
    ["📈 Trend", "🔬 Biomarker Contributions", "🎚️ Sensitivity", "📖 About"]
)

# ── Trend ───────────────────────────────────────────────────────────────────
with tab_trend:
    st.subheader("PhenoAge vs Chronological Age")
    st.caption("Wall-clock keeps ticking. The win is bending PhenoAge below it.")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series["date"], y=series["chronological_age"],
        mode="lines+markers", name="Chronological",
        line=dict(color=COLORS["chart_series"][1], width=3, dash="dot"),
        marker=dict(size=8),
    ))
    fig.add_trace(go.Scatter(
        x=series["date"], y=series["pheno_age"],
        mode="lines+markers", name="PhenoAge",
        line=dict(color=COLORS["gold"], width=4),
        marker=dict(size=10),
        fill="tonexty", fillcolor="rgba(76,175,80,0.10)",
    ))
    apply_theme(fig, height=420)
    fig.update_layout(
        yaxis=dict(title="Age (years)"),
        legend=dict(orientation="h", y=1.1, x=0),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Delta — PhenoAge minus Chronological")
    fig_d = go.Figure()
    fig_d.add_trace(go.Bar(
        x=series["date"], y=series["delta"],
        marker=dict(color=[COLORS["success"] if d < 0 else COLORS["danger"]
                           for d in series["delta"]]),
        text=[f"{d:+.1f}" for d in series["delta"]],
        textposition="outside",
    ))
    fig_d.add_hline(y=0, line=dict(color=COLORS["text_muted"], width=1))
    apply_theme(fig_d, height=300)
    fig_d.update_layout(yaxis=dict(title="Years younger / older"), showlegend=False)
    st.plotly_chart(fig_d, use_container_width=True)

# ── Biomarker contributions ─────────────────────────────────────────────────
with tab_breakdown:
    st.subheader("What's Driving Your PhenoAge")
    st.caption("Per Levine 2018 coefficients. Positive contribution = ages you up; negative = ages you down. Age itself is the largest line by design.")

    contrib = latest.contributions.copy()
    # Exclude age itself for a clearer "modifiable levers" view
    age_contrib = contrib.pop("age", 0)
    df_c = pd.DataFrame([
        {"biomarker": k, "contribution": v, "value": latest.inputs_used[k]}
        for k, v in contrib.items()
    ])
    df_c = df_c.sort_values("contribution", ascending=True)

    # Friendly biomarker labels
    labels = {
        "albumin":         "Albumin (g/L)",
        "creatinine":      "Creatinine (µmol/L)",
        "glucose":         "Glucose (mmol/L)",
        "ln_crp":          "ln(hsCRP)",
        "lymphocyte_pct":  "Lymphocytes (%)",
        "mcv":             "MCV (fL)",
        "rdw":             "RDW (%)",
        "alkaline_phos":   "Alkaline phos (U/L)",
        "wbc":             "WBC (10⁹/L)",
    }
    df_c["label"] = df_c["biomarker"].map(labels).fillna(df_c["biomarker"])

    fig_c = go.Figure(go.Bar(
        x=df_c["contribution"], y=df_c["label"],
        orientation="h",
        marker=dict(color=[COLORS["danger"] if v > 0 else COLORS["success"]
                           for v in df_c["contribution"]]),
        text=[f"{v:+.3f}  ({val:.2f})" for v, val in zip(df_c["contribution"], df_c["value"])],
        textposition="outside",
    ))
    apply_theme(fig_c, height=420)
    fig_c.update_layout(
        xaxis=dict(title="Contribution to xb (negative = younger)"),
        yaxis=dict(title=""),
        showlegend=False,
    )
    st.plotly_chart(fig_c, use_container_width=True)

    st.markdown(f"**Age contribution (fixed):** `{age_contrib:+.3f}` from chronological age {latest.chronological_age:.1f}y")
    st.markdown(f"**Intercept:** `{COEFFS['intercept']:+.3f}`")
    st.markdown(f"**Raw xb total:** `{latest.xb:+.3f}` → 10-yr mortality {latest.mortality_score*100:.2f}% → PhenoAge **{latest.pheno_age:.1f} y**")

# ── Sensitivity / levers ────────────────────────────────────────────────────
with tab_levers:
    st.subheader("Move a Lever, See the Impact")
    st.caption("Slide each biomarker to a different value and watch PhenoAge update. Useful for setting targets.")

    inputs = latest.inputs_used
    # Provide current values back in lab-unit space for the UI
    pivot = bw.pivot_table(index="date", columns="biomarker_canonical",
                            values="value", aggfunc="last").reset_index()
    last_row = pivot.iloc[-1]

    c1, c2, c3 = st.columns(3)
    with c1:
        albumin = st.slider("Albumin (g/dL)", 3.0, 5.5, float(last_row["albumin_g_dl"]), 0.1)
        creat = st.slider("Creatinine (mg/dL)", 0.5, 2.0, float(last_row["creatinine_mg_dl"]), 0.05)
        glucose = st.slider("Glucose (mg/dL)", 70, 140, int(last_row["glucose_mg_dl"]), 1)
    with c2:
        crp = st.slider("hsCRP (mg/L)", 0.1, 5.0, float(last_row["hscrp_mg_l"]), 0.1)
        lymph = st.slider("Lymphocytes (%)", 15.0, 50.0, float(last_row["lymphocytes_pct"]), 0.5)
        mcv = st.slider("MCV (fL)", 80.0, 100.0, float(last_row["mcv_fl"]), 0.5)
    with c3:
        rdw = st.slider("RDW (%)", 11.0, 16.0, float(last_row["rdw_pct"]), 0.1)
        alp = st.slider("Alkaline phos (U/L)", 40, 130, int(last_row["alp_u_l"]), 1)
        wbc = st.slider("WBC (10³/µL)", 3.0, 11.0, float(last_row["wbc_k_ul"]), 0.1)

    sim = compute_phenoage(
        age_years=latest.chronological_age,
        albumin_g_dl=albumin,
        creatinine_mg_dl=creat,
        glucose_mg_dl=glucose,
        crp_mg_L=crp,
        lymphocyte_pct=lymph,
        mcv_fl=mcv,
        rdw_pct=rdw,
        alkaline_phos_u_l=alp,
        wbc_k_ul=wbc,
    )

    sim_delta = sim.pheno_age - latest.pheno_age
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Simulated PhenoAge", f"{sim.pheno_age:.1f} y", f"{sim_delta:+.2f} y vs current")
    with c2:
        st.metric("vs Chronological", f"{sim.delta:+.1f} y", f"current {latest.delta:+.1f}")
    with c3:
        st.metric("10-yr Mortality", f"{sim.mortality_score*100:.2f}%",
                  f"{(sim.mortality_score-latest.mortality_score)*100:+.2f} pts",
                  delta_color="inverse")

# ── About ───────────────────────────────────────────────────────────────────
with tab_about:
    st.markdown("""
### About Levine PhenoAge

[Levine et al. 2018](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5940111/),
*"An epigenetic biomarker of aging for lifespan and healthspan"*, Aging.

PhenoAge is a **linear composite** of 9 routine clinical chemistry markers
plus chronological age, fit against NHANES mortality data. The output is
**predicted age** under a Gompertz mortality model — i.e., the age of an
average person with your same 10-year mortality probability.

### The 9 Inputs

| Marker | Units (Levine) | Direction |
|---|---|---|
| Albumin | g/L | ⬇ lower ages up |
| Creatinine | µmol/L | ⬆ higher ages up |
| Glucose | mmol/L | ⬆ higher ages up |
| hsCRP | ln(mg/L) | ⬆ higher ages up |
| Lymphocyte % | % | ⬇ lower ages up |
| MCV | fL | ⬆ higher ages up |
| RDW | % | ⬆ higher ages up |
| Alkaline phos | U/L | ⬆ higher ages up |
| WBC | 10⁹/L | ⬆ higher ages up |

### Interpretation

| Δ (Pheno − Chrono) | Read |
|---|---|
| < −5 y | Aging slowly — keep stacking |
| −5 to 0 | Younger than time — solid |
| 0 to +5 | Aging on schedule — room to improve |
| > +5 | Aging fast — modifiable levers matter |

### Caveats

- **Not a diagnostic tool.** PhenoAge is a population-level mortality
  proxy, not a personalized clinical prediction.
- **Sensitive to acute inflammation.** A single high CRP draw can swing
  the score. Re-check before reacting.
- **Won't replace DunedinPACE or methylation-based clocks** — but
  it's free, computable from any standard CMP + CBC + hsCRP, and the
  longitudinal trend is what matters.
""")
