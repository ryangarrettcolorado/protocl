"""Bloodwork — panels grouped by system, drill-down per biomarker."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import (
    load_data, refresh_data, append_row,
    latest_bloodwork_draw, previous_bloodwork_draw,
)
from modules.charts import (
    COLORS, apply_theme, time_series, sparkline,
    status_label, status_badge_html, metric_card_html, tier_badge_html,
)
from modules.reference_ranges import load_reference, panel_label
from modules.biomarker_aliases import display_name, canonicalize, ALIASES


st.set_page_config(page_title="Bloodwork · Protocōl", page_icon="⚗️", layout="wide")



from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Bloodwork")
    st.caption("Panels by system · expert-derived optimal ranges · drill into any biomarker")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()


data = load_data()
ref = load_reference()
bw = data.bloodwork

if bw.empty:
    st.warning("No bloodwork yet. Add a draw using the form below or import a CSV from the Imports page.")


# ────────────────────────────────────────────────────────────────────────────
# Draw-level KPI row
# ────────────────────────────────────────────────────────────────────────────

latest = latest_bloodwork_draw(bw)
prev = previous_bloodwork_draw(bw)

if not latest.empty:
    last_date = latest["date"].iloc[0]
    days_ago = (pd.Timestamp("2026-05-25") - last_date).days

    # Count tracked vs in optimal
    tracked = 0
    in_optimal = 0
    in_risk = 0
    for _, row in latest.iterrows():
        r = ref.get(row["biomarker_canonical"])
        if r is None:
            continue
        tracked += 1
        s = status_label(row["value"], r.get("optimal_low"), r.get("optimal_high"),
                         r.get("lab_low"), r.get("lab_high"))
        if s == "Optimal":
            in_optimal += 1
        elif s == "Risk":
            in_risk += 1

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(metric_card_html("Last Draw", last_date.strftime("%b %d, %Y"), f"{days_ago} days ago"), unsafe_allow_html=True)
    with k2:
        st.markdown(metric_card_html("Tracked Biomarkers", f"{tracked}", "with optimal ranges"), unsafe_allow_html=True)
    with k3:
        pct = int(in_optimal / tracked * 100) if tracked else 0
        st.markdown(metric_card_html("In Optimal Range", f"{in_optimal}/{tracked}", f"{pct}%", True), unsafe_allow_html=True)
    with k4:
        st.markdown(metric_card_html("Out of Lab Range", f"{in_risk}", "needs attention", in_risk == 0), unsafe_allow_html=True)

    st.markdown("")


# ────────────────────────────────────────────────────────────────────────────
# Panel-grouped biomarker tables
# ────────────────────────────────────────────────────────────────────────────

if not latest.empty:
    panels_in_data = sorted(latest["panel"].unique().tolist())
    pretty = [panel_label(p) for p in panels_in_data]

    # Tabs per panel + a drill-down tab
    tabs = st.tabs(pretty + ["🔍 Biomarker Drill-down", "+ Add Draw"])

    for i, panel_key in enumerate(panels_in_data):
        with tabs[i]:
            sub_latest = latest[latest["panel"] == panel_key].copy()
            rows = []
            for _, row in sub_latest.iterrows():
                bm = row["biomarker_canonical"]
                r = ref.get(bm, {})
                opt_lo, opt_hi = r.get("optimal_low"), r.get("optimal_high")
                lab_lo, lab_hi = r.get("lab_low") or row.get("lab_ref_low"), r.get("lab_high") or row.get("lab_ref_high")
                s = status_label(row["value"], opt_lo, opt_hi, lab_lo, lab_hi)

                # Previous value
                prev_val = None
                if not prev.empty:
                    pr = prev[prev["biomarker_canonical"] == bm]
                    if not pr.empty:
                        prev_val = pr["value"].iloc[0]
                delta = (row["value"] - prev_val) if prev_val is not None else None
                arrow = "—"
                if delta is not None:
                    arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")

                # Sparkline values
                history = bw[bw["biomarker_canonical"] == bm].sort_values("date")["value"].tolist()

                rows.append({
                    "Biomarker": display_name(bm),
                    "Value": f"{row['value']} {row['unit']}",
                    "Δ": f"{arrow} {abs(delta):.2f}" if delta is not None else "—",
                    "Optimal Range": f"{opt_lo}–{opt_hi}" if opt_lo is not None else "—",
                    "Lab Range": f"{lab_lo}–{lab_hi}" if lab_lo is not None else "—",
                    "Status": s,
                    "Source": r.get("source", "—"),
                    "Tier": r.get("tier", "—"),
                    "_history": history,
                    "_url": r.get("source_url", ""),
                })

            if not rows:
                st.info(f"No biomarkers in the {panel_label(panel_key)} panel yet.")
                continue

            df = pd.DataFrame(rows)
            df_display = df.drop(columns=["_history", "_url"])

            # Render with status color emphasis
            def style_status(val):
                colors = {"Optimal": "#4CAF50", "Monitor": "#FF9800", "Risk": "#F44336"}
                c = colors.get(val, "#A0A0A0")
                return f"color: {c}; font-weight: 600"

            styled = df_display.style.map(style_status, subset=["Status"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    # Drill-down tab
    with tabs[len(panels_in_data)]:
        st.markdown("#### Biomarker Drill-down")
        all_bms = sorted(bw["biomarker_canonical"].unique().tolist())
        all_pretty = [display_name(b) for b in all_bms]
        choice_idx = st.selectbox(
            "Choose a biomarker",
            range(len(all_bms)),
            format_func=lambda i: all_pretty[i],
            index=all_bms.index("testosterone_total_ng_dl") if "testosterone_total_ng_dl" in all_bms else 0,
        )
        bm = all_bms[choice_idx]
        sub = bw[bw["biomarker_canonical"] == bm].sort_values("date").copy()
        r = ref.get(bm, {})

        # Source / tier banner
        if r:
            tb = tier_badge_html(r.get("tier", "T5"))
            url = r.get("source_url", "#")
            st.markdown(
                f'<div style="margin-bottom:12px;color:{COLORS["text_muted"]};font-size:0.9rem">'
                f'Optimal range: <span style="color:{COLORS["gold"]};font-weight:600">{r.get("optimal_low")}–{r.get("optimal_high")} {r.get("unit","")}</span> · '
                f'Source: <a href="{url}" target="_blank" style="color:{COLORS["text_primary"]}">{r.get("source","—")}</a> · {tb}'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Time series chart with both range bands and protocol overlays
        fig = time_series(
            sub.rename(columns={"date": "date", "value": "value"}),
            x="date", y="value",
            title=None,
            optimal_low=r.get("optimal_low"), optimal_high=r.get("optimal_high"),
            lab_low=r.get("lab_low"), lab_high=r.get("lab_high"),
            unit=r.get("unit", ""),
            height=420,
        )

        # Overlay protocol start dates as vertical dashed lines
        if not data.protocol.empty:
            CAT_COLORS = {"hormone": "#FFB612", "peptide": "#4FC3F7",
                          "supplement": "#81C784", "medication": "#FF8A65"}
            for _, item in data.protocol.iterrows():
                try:
                    fig.add_vline(
                        x=pd.to_datetime(item["start_date"]),
                        line=dict(color=CAT_COLORS.get(item["category"], COLORS["text_faint"]),
                                  width=1, dash="dash"),
                        annotation_text=item["name"][:14],
                        annotation_position="top",
                        annotation_font_size=8,
                        annotation_font_color=COLORS["text_muted"],
                    )
                except Exception:
                    continue

        st.plotly_chart(fig, use_container_width=True)

        # Statistical trend line + summary
        if len(sub) >= 3:
            x_num = np.arange(len(sub))
            slope, intercept = np.polyfit(x_num, sub["value"].astype(float), 1)
            trend_dir = "improving" if (slope > 0 and r.get("optimal_high", 0) > sub["value"].mean()) or \
                                       (slope < 0 and r.get("optimal_high", 0) < sub["value"].mean()) else "see chart"
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(metric_card_html("Latest", f"{sub['value'].iloc[-1]:.2f}", r.get("unit", "")), unsafe_allow_html=True)
            with c2: st.markdown(metric_card_html("Mean", f"{sub['value'].mean():.2f}", "all draws"), unsafe_allow_html=True)
            with c3: st.markdown(metric_card_html("Range", f"{sub['value'].min():.1f}–{sub['value'].max():.1f}", "min–max"), unsafe_allow_html=True)
            with c4: st.markdown(metric_card_html("Trend", f"{slope:+.2f}/draw", "per draw"), unsafe_allow_html=True)

        # Raw history table
        st.markdown("##### History")
        hist = sub[["date", "value", "unit", "source_lab", "notes"]].copy()
        hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(hist.rename(columns={"date": "Date", "value": "Value", "unit": "Unit",
                                          "source_lab": "Lab", "notes": "Notes"}),
                     use_container_width=True, hide_index=True)

    # Add draw tab
    with tabs[-1]:
        st.markdown("#### Add a Bloodwork Value")
        with st.form("add_bloodwork", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                d_date = st.date_input("Draw date", value=datetime(2026, 5, 25).date())
                source_lab = st.text_input("Lab", placeholder="LabCorp / Quest / ...")
            with c2:
                bm_options = sorted([display_name(k) for k in ref.keys()])
                bm_name = st.selectbox("Biomarker", bm_options)
                # Reverse map
                canonical = None
                for k in ref.keys():
                    if display_name(k) == bm_name:
                        canonical = k
                        break
                value = st.number_input("Value", value=0.0, step=0.01, format="%.2f")
            with c3:
                if canonical and canonical in ref:
                    st.markdown(f"Unit: **{ref[canonical].get('unit','')}**")
                    st.caption(f"Optimal: {ref[canonical].get('optimal_low')}–{ref[canonical].get('optimal_high')}")
                notes = st.text_area("Notes")

            submitted = st.form_submit_button("Add value")
            if submitted and canonical:
                r = ref[canonical]
                append_row("bloodwork.csv", {
                    "date": d_date.strftime("%Y-%m-%d"),
                    "panel": r.get("panel", "other"),
                    "biomarker_canonical": canonical,
                    "value": value,
                    "unit": r.get("unit", ""),
                    "lab_ref_low": r.get("lab_low", ""),
                    "lab_ref_high": r.get("lab_high", ""),
                    "source_lab": source_lab,
                    "notes": notes,
                })
                st.success(f"Added {bm_name} = {value} on {d_date}.")
