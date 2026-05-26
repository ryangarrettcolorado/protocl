"""Risks & Alerts — surface biomarkers out-of-range, trending wrong, interactions."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data, latest_bloodwork_draw, previous_bloodwork_draw
from modules.charts import COLORS, apply_theme, metric_card_html, status_label
from modules.reference_ranges import load_reference, get as ref_get
from modules.biomarker_aliases import display_name


st.set_page_config(page_title="Risks · Protocōl", page_icon="⚗️", layout="wide")

from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Risks & Alerts")
    st.caption("Out-of-range biomarkers · adverse trends · protocol interactions")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
bw = data.bloodwork.copy()
ref = load_reference()
protocol = data.protocol.copy()
wearables = data.wearables.copy()

if bw.empty:
    st.info("No bloodwork yet.")
    st.stop()

latest_df = latest_bloodwork_draw(bw)
prev_df = previous_bloodwork_draw(bw)

# ────────────────────────────────────────────────────────────────────────────
# Detect risks
# ────────────────────────────────────────────────────────────────────────────
def classify(row, ref_entry):
    """Return (status, color) where status ∈ optimal / suboptimal / out_of_range."""
    val = row["value"]
    if ref_entry is None:
        return ("unknown", COLORS["text_muted"])
    lab_low, lab_high = ref_entry.get("lab_low"), ref_entry.get("lab_high")
    opt_low, opt_high = ref_entry.get("optimal_low"), ref_entry.get("optimal_high")
    # Out of lab range = critical
    if lab_low is not None and val < lab_low:
        return ("out_of_range_low", COLORS["danger"])
    if lab_high is not None and val > lab_high:
        return ("out_of_range_high", COLORS["danger"])
    # Out of optimal but within lab = suboptimal
    if opt_low is not None and val < opt_low:
        return ("suboptimal_low", COLORS["warning"])
    if opt_high is not None and val > opt_high:
        return ("suboptimal_high", COLORS["warning"])
    return ("optimal", COLORS["success"])


def trend_alert(canonical, bw_df):
    """Detect any biomarker that has moved >15% in a directionally adverse way."""
    sub = bw_df[bw_df["biomarker_canonical"] == canonical].sort_values("date")
    if len(sub) < 2:
        return None
    first = sub.iloc[0]["value"]
    last = sub.iloc[-1]["value"]
    if first == 0:
        return None
    pct = (last - first) / first * 100
    r = ref.get(canonical, {})
    opt_low, opt_high = r.get("optimal_low"), r.get("optimal_high")
    # Adverse direction logic
    adverse = False
    if opt_high is not None and last > opt_high and pct > 5:
        adverse = True
    elif opt_low is not None and last < opt_low and pct < -5:
        adverse = True
    elif abs(pct) > 25:
        adverse = True
    if adverse:
        return {"canonical": canonical, "first": first, "last": last, "pct": pct,
                "first_date": sub.iloc[0]["date"], "last_date": sub.iloc[-1]["date"]}
    return None


risks = []
for _, row in latest_df.iterrows():
    canonical = row["biomarker_canonical"]
    r = ref.get(canonical)
    if r is None:
        continue
    status, color = classify(row, r)
    if status in ("out_of_range_low", "out_of_range_high",
                  "suboptimal_low", "suboptimal_high"):
        # Find delta vs prior draw
        prior = prev_df[prev_df["biomarker_canonical"] == canonical]
        prior_val = prior["value"].iloc[0] if not prior.empty else None
        delta = (row["value"] - prior_val) if prior_val is not None else None
        risks.append({
            "canonical": canonical,
            "panel": r.get("panel"),
            "value": row["value"],
            "unit": r.get("unit"),
            "lab_low": r.get("lab_low"),
            "lab_high": r.get("lab_high"),
            "optimal_low": r.get("optimal_low"),
            "optimal_high": r.get("optimal_high"),
            "status": status,
            "color": color,
            "prior": prior_val,
            "delta": delta,
            "tier": r.get("tier"),
        })

# Sort: critical first, then by tier
risks.sort(key=lambda r: (0 if "out_of_range" in r["status"] else 1, r.get("tier", "T5")))

# Trends
trend_alerts = []
for canonical in latest_df["biomarker_canonical"].unique():
    t = trend_alert(canonical, bw)
    if t:
        trend_alerts.append(t)

# Interaction alerts — simple rule-based
interactions = []
hct_row = latest_df[latest_df["biomarker_canonical"] == "hematocrit_pct"]
on_trt = any("testosterone" in str(n).lower() for n in protocol["name"].fillna(""))
if not hct_row.empty and on_trt:
    hct_val = hct_row["value"].iloc[0]
    if hct_val > 50:
        interactions.append({
            "title": "TRT + Hematocrit creeping high",
            "severity": "high" if hct_val > 52 else "medium",
            "detail": f"HCT {hct_val:.1f}% on TRT. Threshold for phlebotomy ≈ 52%. Consider donation; recheck in 6-8 wks.",
        })

# Add CRP + hsCRP red flags
crp_row = latest_df[latest_df["biomarker_canonical"] == "hscrp_mg_l"]
if not crp_row.empty and crp_row["value"].iloc[0] > 2.0:
    interactions.append({
        "title": "Elevated hsCRP — systemic inflammation",
        "severity": "medium",
        "detail": f"hsCRP {crp_row['value'].iloc[0]:.2f} mg/L > 2.0. Check for infection, recent training stress, or sleep loss. Recheck before reacting.",
    })

# RHR jump
if not wearables.empty:
    w7 = wearables.sort_values("date").tail(7)["resting_hr_bpm"].mean()
    wbase = wearables.sort_values("date").head(14)["resting_hr_bpm"].mean()
    if w7 - wbase > 4:
        interactions.append({
            "title": "Resting HR elevated vs baseline",
            "severity": "medium",
            "detail": f"7d avg RHR {w7:.0f} vs baseline {wbase:.0f}. Could signal under-recovery, infection, or alcohol.",
        })

# ────────────────────────────────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────────────────────────────────
critical = [r for r in risks if "out_of_range" in r["status"]]
suboptimal = [r for r in risks if "suboptimal" in r["status"]]
high_severity_int = [i for i in interactions if i["severity"] == "high"]

kpis = [
    ("OUT OF LAB RANGE", f"{len(critical)}", "needs clinical attention", len(critical) == 0),
    ("SUBOPTIMAL", f"{len(suboptimal)}", "within lab, outside optimal", None),
    ("ADVERSE TRENDS", f"{len(trend_alerts)}", ">15% move wrong way", None),
    ("INTERACTIONS", f"{len(interactions)}", f"{len(high_severity_int)} high severity", len(high_severity_int) == 0),
    ("TOTAL FLAGS", f"{len(risks) + len(trend_alerts) + len(interactions)}", "across all sources", None),
    ("LATEST DRAW", latest_df["date"].iloc[0].strftime("%b %d") if not latest_df.empty else "—",
     f"{(pd.Timestamp('2026-05-25') - latest_df['date'].iloc[0]).days}d ago" if not latest_df.empty else "", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_oor, tab_trends, tab_interactions = st.tabs(
    ["🚩 Out-of-Range", "📈 Adverse Trends", "⚠️ Interactions"]
)

# ── Out-of-range ────────────────────────────────────────────────────────────
with tab_oor:
    if not risks:
        st.success("All measured biomarkers are within optimal range.")
    else:
        for r in risks:
            severity_color = COLORS["danger"] if "out_of_range" in r["status"] else COLORS["warning"]
            severity_label = "OUT OF RANGE" if "out_of_range" in r["status"] else "SUBOPTIMAL"
            with st.container():
                cols = st.columns([3, 2, 2, 2, 1])
                with cols[0]:
                    st.markdown(f"### {display_name(r['canonical'])}")
                    st.caption(f"Panel: {r['panel']} · Tier {r['tier']}")
                with cols[1]:
                    st.metric("Value", f"{r['value']:.2f} {r['unit']}",
                              f"{r['delta']:+.2f} vs prior" if r["delta"] is not None else "no prior")
                with cols[2]:
                    if r["optimal_low"] is not None or r["optimal_high"] is not None:
                        st.markdown(f"**Optimal range**  \n`{r['optimal_low']} – {r['optimal_high']}`")
                with cols[3]:
                    if r["lab_low"] is not None or r["lab_high"] is not None:
                        st.markdown(f"**Lab range**  \n`{r['lab_low']} – {r['lab_high']}`")
                with cols[4]:
                    st.markdown(
                        f'<div style="background:{severity_color}22;color:{severity_color};'
                        f'padding:6px 10px;border-radius:6px;text-align:center;'
                        f'font-weight:600;font-size:0.75rem;">{severity_label}</div>',
                        unsafe_allow_html=True,
                    )
                st.divider()

# ── Trends ──────────────────────────────────────────────────────────────────
with tab_trends:
    if not trend_alerts:
        st.success("No adverse trends detected over the tracked window.")
    else:
        for t in trend_alerts:
            with st.container():
                cols = st.columns([3, 2, 2, 1])
                with cols[0]:
                    st.markdown(f"### {display_name(t['canonical'])}")
                    st.caption(
                        f"{t['first_date'].strftime('%b %Y')} → {t['last_date'].strftime('%b %Y')}"
                    )
                with cols[1]:
                    st.metric("Latest", f"{t['last']:.2f}",
                              f"from {t['first']:.2f}", delta_color="off")
                with cols[2]:
                    st.metric("Δ%", f"{t['pct']:+.1f}%", "across window",
                              delta_color="inverse" if t["pct"] > 0 else "normal")
                with cols[3]:
                    # Sparkline
                    sub = bw[bw["biomarker_canonical"] == t["canonical"]].sort_values("date")
                    fig_s = go.Figure(go.Scatter(
                        x=sub["date"], y=sub["value"], mode="lines+markers",
                        line=dict(color=COLORS["warning"], width=2),
                        marker=dict(size=6),
                    ))
                    fig_s.update_layout(
                        height=80, margin=dict(l=0, r=0, t=0, b=0),
                        paper_bgcolor="rgba(0,0,0,0)",
                        plot_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False),
                        yaxis=dict(visible=False),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_s, use_container_width=True,
                                     config={"displayModeBar": False})
                st.divider()

# ── Interactions ────────────────────────────────────────────────────────────
with tab_interactions:
    if not interactions:
        st.success("No protocol or recovery interactions flagged.")
    else:
        for i in interactions:
            color = COLORS["danger"] if i["severity"] == "high" else COLORS["warning"]
            st.markdown(
                f'<div style="background:{color}15;border-left:4px solid {color};'
                f'padding:14px 18px;border-radius:6px;margin-bottom:12px;">'
                f'<div style="display:flex;justify-content:space-between;">'
                f'<strong style="font-size:1.05rem;">{i["title"]}</strong>'
                f'<span style="color:{color};font-size:0.75rem;font-weight:600;">'
                f'{i["severity"].upper()}</span></div>'
                f'<div style="margin-top:6px;color:{COLORS["text_muted"]};font-size:0.9rem;">'
                f'{i["detail"]}</div></div>',
                unsafe_allow_html=True,
            )
