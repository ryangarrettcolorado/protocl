"""Bloodwork — single-page grouped layout (v1.5 canonical pattern).

Sticky filter bar (date range · panel multi-select · marker search) followed by
collapsible sections — one per panel + Drill-down + Add Draw — instead of tabs.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from modules.data_loader import (
    load_data, refresh_data, append_row,
    latest_bloodwork_draw, previous_bloodwork_draw,
)
from modules.charts import (
    COLORS, time_series,
    status_label, metric_card_html, tier_badge_html,
)
from modules.reference_ranges import load_reference, panel_label
from modules.biomarker_aliases import display_name
from modules.theme import inject_css, render_section_header
from modules.preferences import load_preferences

# ────────────────────────────────────────────────────────────────────────────
# Page shell — no set_page_config (nav owns it); no sidebar brand (top brand)
# ────────────────────────────────────────────────────────────────────────────

inject_css()

prefs = load_preferences()

col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Bloodwork")
    st.caption("Panels by system · expert-derived optimal ranges · drill into any biomarker")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True, key="bw_refresh"):
        refresh_data()

data = load_data()
ref = load_reference()
bw = data.bloodwork

if bw.empty:
    st.warning("No bloodwork yet. Add a draw in the **Add Draw** section below or import a CSV from the Imports page.")
    st.stop()

# ────────────────────────────────────────────────────────────────────────────
# Sticky filter bar
# ────────────────────────────────────────────────────────────────────────────

today = pd.Timestamp("2026-05-25")
min_date = bw["date"].min().date() if not bw.empty else (today - pd.Timedelta(days=365)).date()
max_date = bw["date"].max().date() if not bw.empty else today.date()

st.markdown('<div class="protocl-sticky-filter">', unsafe_allow_html=True)
f1, f2, f3 = st.columns([2, 3, 2])
with f1:
    date_range = st.date_input(
        "Date range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
        key="bw_date_range",
    )
with f2:
    all_panels = sorted(bw["panel"].dropna().unique().tolist())
    panel_pretty_map = {panel_label(p): p for p in all_panels}
    selected_pretty = st.multiselect(
        "Panels",
        options=list(panel_pretty_map.keys()),
        default=list(panel_pretty_map.keys()),
        key="bw_panel_filter",
    )
    selected_panels = [panel_pretty_map[p] for p in selected_pretty]
with f3:
    marker_query = st.text_input("Search markers", placeholder="apoB, hsCRP, …", key="bw_marker_search")
st.markdown('</div>', unsafe_allow_html=True)

# Apply filters
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_d = pd.Timestamp(date_range[0])
    end_d = pd.Timestamp(date_range[1])
    bw_filtered = bw[(bw["date"] >= start_d) & (bw["date"] <= end_d)].copy()
else:
    bw_filtered = bw.copy()

if selected_panels:
    bw_filtered = bw_filtered[bw_filtered["panel"].isin(selected_panels)]

if marker_query:
    q = marker_query.strip().lower()
    bw_filtered = bw_filtered[
        bw_filtered["biomarker_canonical"].str.lower().str.contains(q, na=False)
        | bw_filtered["biomarker_canonical"].apply(lambda b: q in display_name(b).lower())
    ]

latest = latest_bloodwork_draw(bw_filtered) if not bw_filtered.empty else bw_filtered
prev = previous_bloodwork_draw(bw_filtered) if not bw_filtered.empty else bw_filtered

# ────────────────────────────────────────────────────────────────────────────
# Draw-level KPI row
# ────────────────────────────────────────────────────────────────────────────

if not latest.empty:
    last_date = latest["date"].iloc[0]
    days_ago = (today - last_date).days

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
# Panel-grouped sections (collapsible)
# ────────────────────────────────────────────────────────────────────────────

PANEL_ICONS = {
    "cardiovascular": "❤️",
    "glucose": "🩸",
    "hormonal_sex": "⚡",
    "hormonal_thyroid": "🦋",
    "inflammation": "🔥",
    "hematology": "🩹",
    "liver_kidney": "🫘",
    "nutrient": "💊",
}

if not latest.empty:
    panels_in_data = sorted(latest["panel"].unique().tolist())

    for panel_key in panels_in_data:
        sub_latest = latest[latest["panel"] == panel_key].copy()
        if sub_latest.empty:
            continue

        # Build rows + count statuses for the chip row
        rows = []
        c_opt = c_mon = c_risk = 0
        for _, row in sub_latest.iterrows():
            bm = row["biomarker_canonical"]
            r = ref.get(bm, {})
            opt_lo, opt_hi = r.get("optimal_low"), r.get("optimal_high")
            lab_lo, lab_hi = r.get("lab_low") or row.get("lab_ref_low"), r.get("lab_high") or row.get("lab_ref_high")
            s = status_label(row["value"], opt_lo, opt_hi, lab_lo, lab_hi)
            if s == "Optimal": c_opt += 1
            elif s == "Monitor": c_mon += 1
            elif s == "Risk": c_risk += 1

            prev_val = None
            if not prev.empty:
                pr = prev[prev["biomarker_canonical"] == bm]
                if not pr.empty:
                    prev_val = pr["value"].iloc[0]
            delta = (row["value"] - prev_val) if prev_val is not None else None
            arrow = "—"
            if delta is not None:
                arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")

            rows.append({
                "Biomarker": display_name(bm),
                "Value": f"{row['value']} {row['unit']}",
                "Δ": f"{arrow} {abs(delta):.2f}" if delta is not None else "—",
                "Optimal Range": f"{opt_lo}–{opt_hi}" if opt_lo is not None else "—",
                "Lab Range": f"{lab_lo}–{lab_hi}" if lab_lo is not None else "—",
                "Status": s,
                "Source": r.get("source", "—"),
                "Tier": r.get("tier", "—"),
            })

        # Status chips for header
        chips = []
        if c_opt: chips.append(f'<span class="alert-chip alert-chip-ok">{c_opt} optimal</span>')
        if c_mon: chips.append(f'<span class="alert-chip alert-chip-warn">{c_mon} monitor</span>')
        if c_risk: chips.append(f'<span class="alert-chip alert-chip-risk">{c_risk} risk</span>')
        chips_html = " ".join(chips)

        icon = PANEL_ICONS.get(panel_key, "🧪")
        label = panel_label(panel_key)

        render_section_header(icon, label, count_text=f"{len(rows)} markers", chips_html=chips_html)
        with st.expander(f"{label} — details", expanded=True):
            if not rows:
                st.info(f"No biomarkers in the {label} panel yet.")
                continue

            df = pd.DataFrame(rows)

            def style_status(val):
                colors = {"Optimal": "#4CAF50", "Monitor": "#FF9800", "Risk": "#F44336"}
                c = colors.get(val, "#A0A0A0")
                return f"color: {c}; font-weight: 600"

            styled = df.style.map(style_status, subset=["Status"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────────────
# Biomarker drill-down
# ────────────────────────────────────────────────────────────────────────────

render_section_header("🔍", "Biomarker Drill-down", count_text="time series + range bands")
with st.expander("Biomarker drill-down — details", expanded=False):
    all_bms = sorted(bw["biomarker_canonical"].unique().tolist())
    if not all_bms:
        st.info("No biomarkers available yet.")
    else:
        all_pretty = [display_name(b) for b in all_bms]
        default_idx = all_bms.index("testosterone_total_ng_dl") if "testosterone_total_ng_dl" in all_bms else 0
        choice_idx = st.selectbox(
            "Choose a biomarker",
            range(len(all_bms)),
            format_func=lambda i: all_pretty[i],
            index=default_idx,
            key="bw_drill_select",
        )
        bm = all_bms[choice_idx]
        sub = bw[bw["biomarker_canonical"] == bm].sort_values("date").copy()
        r = ref.get(bm, {})

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

        fig = time_series(
            sub.rename(columns={"date": "date", "value": "value"}),
            x="date", y="value",
            title=None,
            optimal_low=r.get("optimal_low"), optimal_high=r.get("optimal_high"),
            lab_low=r.get("lab_low"), lab_high=r.get("lab_high"),
            unit=r.get("unit", ""),
            height=420,
        )

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

        if len(sub) >= 3:
            x_num = np.arange(len(sub))
            slope, _intercept = np.polyfit(x_num, sub["value"].astype(float), 1)
            c1, c2, c3, c4 = st.columns(4)
            with c1: st.markdown(metric_card_html("Latest", f"{sub['value'].iloc[-1]:.2f}", r.get("unit", "")), unsafe_allow_html=True)
            with c2: st.markdown(metric_card_html("Mean", f"{sub['value'].mean():.2f}", "all draws"), unsafe_allow_html=True)
            with c3: st.markdown(metric_card_html("Range", f"{sub['value'].min():.1f}–{sub['value'].max():.1f}", "min–max"), unsafe_allow_html=True)
            with c4: st.markdown(metric_card_html("Trend", f"{slope:+.2f}/draw", "per draw"), unsafe_allow_html=True)

        st.markdown("##### History")
        hist = sub[["date", "value", "unit", "source_lab", "notes"]].copy()
        hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
        st.dataframe(hist.rename(columns={"date": "Date", "value": "Value", "unit": "Unit",
                                          "source_lab": "Lab", "notes": "Notes"}),
                     use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────────────
# Add Draw
# ────────────────────────────────────────────────────────────────────────────

render_section_header("➕", "Add Draw", count_text="manual entry")
with st.expander("Add a bloodwork value", expanded=False):
    with st.form("add_bloodwork", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            d_date = st.date_input("Draw date", value=datetime(2026, 5, 25).date(), key="bw_add_date")
            source_lab = st.text_input("Lab", placeholder="LabCorp / Quest / ...", key="bw_add_lab")
        with c2:
            bm_options = sorted([display_name(k) for k in ref.keys()])
            bm_name = st.selectbox("Biomarker", bm_options, key="bw_add_bm")
            canonical = None
            for k in ref.keys():
                if display_name(k) == bm_name:
                    canonical = k
                    break
            value = st.number_input("Value", value=0.0, step=0.01, format="%.2f", key="bw_add_value")
        with c3:
            if canonical and canonical in ref:
                st.markdown(f"Unit: **{ref[canonical].get('unit','')}**")
                st.caption(f"Optimal: {ref[canonical].get('optimal_low')}–{ref[canonical].get('optimal_high')}")
            notes = st.text_area("Notes", key="bw_add_notes")

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
