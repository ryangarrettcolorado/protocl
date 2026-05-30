"""Protocol — active interventions, timeline, change log, effectiveness."""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data, append_row
from modules.charts import COLORS, apply_theme, metric_card_html, full_height
from modules.biomarker_aliases import display_name
from explainers.ui import explainer_block


from modules.theme import inject_css, grouped_sections
inject_css()
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Protocol")
    st.caption("Active interventions, cycle tracking, and cause-and-effect analysis")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()


data = load_data()
protocol = data.protocol.copy()

if protocol.empty:
    st.warning("No protocol items yet. Add one below.")
    st.stop()

TODAY = pd.Timestamp("2026-05-25")

# Split active vs historical
active = protocol[protocol["end_date"].isna()].copy()
historical = protocol[protocol["end_date"].notna()].copy()

# Category color map for Gantt
CAT_COLORS = {
    "hormone":     "#FFB612",
    "peptide":     "#4FC3F7",
    "supplement":  "#81C784",
    "medication":  "#FF8A65",
    "probiotic":   "#CE93D8",
    "other":       "#80DEEA",
}


# ────────────────────────────────────────────────────────────────────────────
# KPI row
# ────────────────────────────────────────────────────────────────────────────

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(metric_card_html("Active Items", f"{len(active)}", f"{len(active['category'].unique())} categories"), unsafe_allow_html=True)
with k2:
    avg_adh = active["adherence_pct"].mean() if not active.empty else 0
    st.markdown(metric_card_html("Avg Adherence", f"{int(avg_adh)}%", "across active"), unsafe_allow_html=True)
with k3:
    hormones = len(active[active["category"].isin(["hormone", "peptide"])])
    st.markdown(metric_card_html("Hormones + Peptides", f"{hormones}", "TRT + peptide cycles"), unsafe_allow_html=True)
with k4:
    days_on_longest = 0
    if not active.empty:
        days_on_longest = (TODAY - pd.to_datetime(active["start_date"]).min()).days
    st.markdown(metric_card_html("Longest Active", f"{days_on_longest}d", "core supplement"), unsafe_allow_html=True)


st.markdown("")


# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────

tab_active, tab_timeline, tab_log, tab_effect, tab_add = grouped_sections(
    ["Active Protocol", "Timeline (Gantt)", "Change Log", "Effectiveness", "+ Add Item"]
)


# ── Active Protocol ───────────────────────────────────────────────────────
def _infer_protocol_category(category: str | None, name: str | None) -> str:
    """Map the raw `category` column to one of the five display buckets.

    Falls back to keyword matching on `name` if the row lacks a recognized
    category — covers hand-imported rows where `category` is blank.
    """
    cat = (category or "").strip().lower()
    nm = (name or "").strip().lower()
    if cat in ("hormone", "hormonal"):
        return "Hormonal"
    if cat == "peptide":
        return "Peptides"
    if cat == "supplement":
        return "Supplements"
    if cat in ("medication", "med", "drug", "pharma"):
        return "Medications"
    if cat in ("probiotic",):
        return "Supplements"
    # Inference from name when category is missing/unknown.
    hormone_hits = ("testosterone", "estradiol", "anastrozole", "hcg", "progesterone",
                     "dhea", "thyroid", "t3", "t4", "trt", "cypionate", "enanthate")
    peptide_hits = ("ipamorelin", "cjc", "bpc", "tb-500", "tb500", "sermorelin",
                     "ghrp", "ghk", "mots-c", "epitalon", "semax", "selank")
    med_hits = ("metformin", "rapamycin", "statin", "atorvastatin", "ezetimibe",
                 "ozempic", "tirzepatide", "semaglutide", "tadalafil", "finasteride",
                 "sildenafil")
    if any(k in nm for k in hormone_hits):
        return "Hormonal"
    if any(k in nm for k in peptide_hits):
        return "Peptides"
    if any(k in nm for k in med_hits):
        return "Medications"
    if cat in ("supplement", ""):
        return "Supplements"
    return "Other"


with tab_active:
    if active.empty:
        st.info("No active items.")
    else:
        active_display = active.copy()
        active_display["_bucket"] = active_display.apply(
            lambda r: _infer_protocol_category(r.get("category"), r.get("name")), axis=1
        )

        CATEGORY_TABS = ["Hormonal", "Peptides", "Supplements", "Medications", "Other"]
        # Show counts in tab labels so empty buckets are obvious.
        counts = active_display["_bucket"].value_counts().to_dict()
        cat_tabs = st.tabs([f"{c} ({counts.get(c, 0)})" for c in CATEGORY_TABS])

        for tab, cat_name in zip(cat_tabs, CATEGORY_TABS):
            with tab:
                sub = active_display[active_display["_bucket"] == cat_name]
                if sub.empty:
                    st.caption(f"No active {cat_name.lower()} items.")
                    continue
                display = sub[[
                    "category", "name", "dose", "unit", "frequency", "route",
                    "timing", "reason", "prescriber", "adherence_pct", "start_date"
                ]].copy()
                display["start_date"] = pd.to_datetime(display["start_date"]).dt.strftime("%Y-%m-%d")
                display["days_on"] = (TODAY - pd.to_datetime(sub["start_date"])).dt.days.values
                display = display.rename(columns={
                    "category": "Category", "name": "Name", "dose": "Dose", "unit": "Unit",
                    "frequency": "Frequency", "route": "Route", "timing": "Timing",
                    "reason": "Reason", "prescriber": "Prescriber",
                    "adherence_pct": "Adherence %", "start_date": "Started", "days_on": "Days On",
                })
                # Fixed row height of 35px + 38px header keeps every row visible without scroll.
                row_h = 35 * len(display) + 38
                st.dataframe(
                    display,
                    use_container_width=True,
                    hide_index=True,
                    height=min(row_h, 1200),
                    column_config={
                        "Adherence %": st.column_config.ProgressColumn(
                            "Adherence %", format="%d%%", min_value=0, max_value=100
                        ),
                        "Days On": st.column_config.NumberColumn("Days On", format="%d"),
                    },
                )
                st.caption(f"{len(display)} row(s)")

        explainer_block("supplement_adherence", chart_data={
            "avg_adherence_pct": round(float(active["adherence_pct"].mean()), 0) if not active.empty else None,
            "active_count": int(len(active)),
            "items": [
                {"name": str(r["name"]), "category": str(r.get("category", "")),
                 "adherence_pct": (None if pd.isna(r.get("adherence_pct")) else round(float(r["adherence_pct"]), 0))}
                for _, r in active_display.iterrows()
            ][:40],
        })

        # Cycle tracker for hormones / peptides
        st.markdown("#### Cycle Tracker")
        cycles = active[active["category"].isin(["hormone", "peptide"])]
        if cycles.empty:
            st.caption("No active hormone or peptide cycles.")
        else:
            for _, item in cycles.iterrows():
                start = pd.to_datetime(item["start_date"])
                days_on = (TODAY - start).days
                weeks_on = days_on / 7
                cat_color = CAT_COLORS.get(item["category"], COLORS["gold"])
                st.markdown(
                    f'<div class="rec-card">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<div><span style="color:{cat_color};font-weight:600">{item["name"]}</span>'
                    f' <span style="color:{COLORS["text_muted"]};font-size:0.85rem">({item["category"]})</span></div>'
                    f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem">Week {int(weeks_on)} · Day {days_on}</div>'
                    f'</div>'
                    f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem;margin-top:4px">'
                    f'{item["dose"]} {item["unit"]} · {item["frequency"]} · {item["route"]}'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        trt = active[active["name"].str.contains("testosterone", case=False, na=False)]
        explainer_block("trt_injection_timing", chart_data={
            "trt_items": [
                {"name": str(r["name"]), "dose": str(r.get("dose", "")),
                 "unit": str(r.get("unit", "")), "frequency": str(r.get("frequency", "")),
                 "route": str(r.get("route", "")), "timing": str(r.get("timing", ""))}
                for _, r in trt.iterrows()
            ],
        })


# ── Gantt timeline ────────────────────────────────────────────────────────
with tab_timeline:
    if protocol.empty:
        st.info("No protocol items.")
    else:
        gantt_df = protocol.copy()
        # Fill missing end dates with today for active items
        gantt_df["end_for_chart"] = gantt_df["end_date"].fillna(TODAY)
        gantt_df["start_for_chart"] = pd.to_datetime(gantt_df["start_date"])
        gantt_df = gantt_df.sort_values("start_for_chart")

        fig = px.timeline(
            gantt_df,
            x_start="start_for_chart",
            x_end="end_for_chart",
            y="name",
            color="category",
            color_discrete_map=CAT_COLORS,
            hover_data={"dose": True, "unit": True, "frequency": True, "reason": True,
                        "start_for_chart": False, "end_for_chart": False},
        )
        fig.update_yaxes(autorange="reversed")

        # Add bloodwork draw markers (plotly add_vline expects ms-since-epoch on datetime axes)
        if not data.bloodwork.empty:
            for draw_date in pd.to_datetime(data.bloodwork["date"]).dropna().unique():
                try:
                    fig.add_vline(
                        x=pd.Timestamp(draw_date).timestamp() * 1000,
                        line=dict(color=COLORS["gold"], width=1, dash="dash"),
                        annotation_text="🩸",
                        annotation_position="top",
                    )
                except Exception:
                    # Older plotly versions can reject ms ints on this axis; skip silently.
                    pass

        apply_theme(fig, height=max(400, 35 * len(gantt_df)))
        fig.update_layout(
            xaxis_title="",
            yaxis_title="",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption("🩸 markers indicate bloodwork draw dates")


# ── Change log ────────────────────────────────────────────────────────────
with tab_log:
    st.markdown("#### Protocol Change History")
    if protocol.empty:
        st.info("No history yet.")
    else:
        # Build event log: every start = added, every end_date present = stopped
        events = []
        for _, row in protocol.iterrows():
            events.append({
                "date": pd.to_datetime(row["start_date"]),
                "event": "Started",
                "name": row["name"],
                "category": row["category"],
                "dose": f"{row['dose']} {row['unit']}",
                "reason": row["reason"],
            })
            if pd.notna(row["end_date"]):
                events.append({
                    "date": pd.to_datetime(row["end_date"]),
                    "event": "Stopped",
                    "name": row["name"],
                    "category": row["category"],
                    "dose": f"{row['dose']} {row['unit']}",
                    "reason": row.get("notes", "") or row["reason"],
                })
        events_df = pd.DataFrame(events).sort_values("date", ascending=False)
        events_df["date"] = events_df["date"].dt.strftime("%Y-%m-%d")
        events_renamed = events_df.rename(columns={
            "date": "Date", "event": "Event", "name": "Item",
            "category": "Category", "dose": "Dose", "reason": "Reason / Notes",
        })
        st.dataframe(
            events_renamed,
            use_container_width=True,
            hide_index=True,
            height=full_height(len(events_renamed)),
        )
        st.caption(f"{len(events_renamed)} row(s)")


# ── Effectiveness panel ───────────────────────────────────────────────────
with tab_effect:
    st.markdown("#### Protocol Effectiveness")
    st.caption("Select a protocol item and a lag window to see how key biomarkers, body comp, and recovery shifted from baseline to post-start.")

    c1, c2 = st.columns([3, 1])
    with c1:
        item_choice = st.selectbox(
            "Protocol item",
            protocol["name"].tolist(),
            index=protocol["name"].tolist().index("Testosterone Cypionate") if "Testosterone Cypionate" in protocol["name"].tolist() else 0,
        )
    with c2:
        lag = st.selectbox("Lag window", [2, 4, 6, 8, 12], index=3, format_func=lambda w: f"{w} weeks")

    item_row = protocol[protocol["name"] == item_choice].iloc[0]
    start = pd.to_datetime(item_row["start_date"])
    cutoff = start + pd.Timedelta(weeks=lag)

    st.markdown(
        f'**Baseline window:** before {start.strftime("%Y-%m-%d")}  ·  '
        f'**Post-intervention window:** {start.strftime("%Y-%m-%d")} through {cutoff.strftime("%Y-%m-%d")}'
    )

    # Biomarker deltas
    deltas = []
    bw = data.bloodwork
    if not bw.empty:
        for bm in bw["biomarker_canonical"].unique():
            sub = bw[bw["biomarker_canonical"] == bm].sort_values("date")
            before = sub[sub["date"] < start]
            after = sub[(sub["date"] >= start) & (sub["date"] <= cutoff)]
            if before.empty or after.empty:
                continue
            b = before["value"].iloc[-1]
            a = after["value"].iloc[-1]
            d = a - b
            pct = (d / b * 100) if b else 0
            deltas.append({
                "Biomarker": display_name(bm),
                "Before": f"{b:.2f}",
                "After": f"{a:.2f}",
                "Δ": f"{d:+.2f}",
                "Δ %": f"{pct:+.1f}%",
                "_pct": pct,
            })

    # Body composition delta
    ib = data.inbody.copy()
    if not ib.empty:
        before_ib = ib[ib["date"] < start]
        after_ib = ib[(ib["date"] >= start) & (ib["date"] <= cutoff)]
        if not before_ib.empty and not after_ib.empty:
            for col, label in [("weight_lbs", "Weight (lbs)"),
                               ("body_fat_pct", "Body Fat %"),
                               ("lean_mass_lbs", "Lean Mass (lbs)")]:
                b = before_ib[col].iloc[-1]
                a = after_ib[col].iloc[-1]
                deltas.append({
                    "Biomarker": label, "Before": f"{b:.1f}", "After": f"{a:.1f}",
                    "Δ": f"{a-b:+.2f}", "Δ %": f"{(a-b)/b*100:+.1f}%",
                    "_pct": (a-b)/b*100,
                })

    if not deltas:
        st.info("Not enough data on either side of the start date to compute deltas.")
    else:
        delta_df = pd.DataFrame(deltas).drop(columns=["_pct"])
        st.dataframe(delta_df, use_container_width=True, hide_index=True,
                     height=full_height(len(delta_df)))
        st.caption(f"{len(delta_df)} row(s)")


# ── Add item form ─────────────────────────────────────────────────────────
with tab_add:
    with st.form("add_protocol", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            category = st.selectbox("Category", ["supplement", "hormone", "peptide", "medication", "probiotic", "other"])
            name = st.text_input("Name", placeholder="e.g. Magnesium Glycinate")
            dose = st.text_input("Dose", placeholder="e.g. 400")
            unit = st.text_input("Unit", placeholder="e.g. mg")
        with c2:
            frequency = st.text_input("Frequency", placeholder="e.g. daily")
            route = st.text_input("Route", placeholder="oral / subq / IM")
            timing = st.text_input("Timing", placeholder="bedtime / with meals")
            prescriber = st.text_input("Prescriber", placeholder="self / Defy Medical")
        with c3:
            start_date = st.date_input("Start date", value=datetime(2026, 5, 25).date())
            reason = st.text_area("Reason", placeholder="Why are you adding this?")
            adherence = st.slider("Expected adherence %", 0, 100, 95)

        submitted = st.form_submit_button("Add protocol item")
        if submitted:
            append_row("protocol.csv", {
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": "",
                "category": category,
                "name": name,
                "dose": dose,
                "unit": unit,
                "frequency": frequency,
                "route": route,
                "timing": timing,
                "reason": reason,
                "prescriber": prescriber,
                "cycle_status": "active",
                "adherence_pct": adherence,
                "notes": "",
            })
            st.success(f"Added {name}.")


with st.expander("📚 Sources Informing Design", expanded=False):
    st.markdown("""
- **Examine.com Supplement Evidence Database** — independent, citation-graded reviews of
  supplement efficacy and safety. [examine.com](https://examine.com)
- **Attia, P.** *Outlive*, Ch. 16 — framework for evaluating supplementation: bias toward
  evidence-backed compounds, avoid stacking, monitor with bloodwork.
- **Endocrine Society Clinical Practice Guideline** — *Testosterone Therapy in Men With
  Hypogonadism* (Bhasin et al., 2018). Guidance for TRT initiation, monitoring (hematocrit,
  PSA, estradiol), and phlebotomy thresholds.
  [academic.oup.com/jcem/article/103/5/1715/4939465](https://academic.oup.com/jcem/article/103/5/1715/4939465)
- **FDA / regulatory caveat on peptides** — many peptides listed in protocol tabs (BPC-157,
  CJC-1295, etc.) are **not** FDA-approved for human therapeutic use and are research-grade.
  Use only under qualified clinical supervision; the regulatory landscape is shifting and
  some compounds may be re-scheduled or restricted by compounding pharmacies.
""")
