"""Timeline — unified chronological event stream across every data source."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.data_loader import load_data, refresh_data
from modules.charts import COLORS, apply_theme, metric_card_html, full_height


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Timeline")
    st.caption("Every event across protocol, bloodwork, body comp, training, and notes")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
TODAY = pd.Timestamp("2026-05-25")

# ────────────────────────────────────────────────────────────────────────────
# Event categories (color-coded)
# ────────────────────────────────────────────────────────────────────────────
CAT_COLORS = {
    "Bloodwork":       COLORS["chart_series"][0],     # primary
    "Protocol start":  COLORS["chart_series"][1],
    "Protocol end":    COLORS["text_muted"],
    "Body comp":       COLORS["chart_series"][2],
    "N=1 experiment":  COLORS["chart_series"][3],
    "Action item":     COLORS["warning"],
    "Context note":    COLORS["chart_series"][4] if len(COLORS["chart_series"]) > 4 else "#A78BFA",
}


def _add_event(rows: list, date, category, title, detail):
    if pd.isna(date):
        return
    rows.append({"date": pd.to_datetime(date), "category": category,
                 "title": title, "detail": detail})


# ────────────────────────────────────────────────────────────────────────────
# Build the unified event stream
# ────────────────────────────────────────────────────────────────────────────
events: list = []

# 1. Bloodwork — one event per unique draw date
if not data.bloodwork.empty:
    for d in sorted(data.bloodwork["date"].dropna().unique()):
        n_markers = data.bloodwork[data.bloodwork["date"] == d].shape[0]
        _add_event(events, d, "Bloodwork", f"Lab draw ({n_markers} biomarkers)",
                   "Quarterly panel")

# 2. Protocol — start + end events
if not data.protocol.empty:
    for _, row in data.protocol.iterrows():
        name = row.get("name", "")
        cat  = row.get("category", "")
        dose = f"{row.get('dose', '')} {row.get('unit', '')}".strip()
        freq = row.get("frequency", "")
        _add_event(events, row.get("start_date"), "Protocol start",
                   f"Start: {name}", f"{cat} · {dose} · {freq}")
        end = row.get("end_date")
        if pd.notna(end):
            _add_event(events, end, "Protocol end",
                       f"End: {name}", f"{cat} · cycle complete")

# 3. InBody scans
if not data.inbody.empty:
    for _, row in data.inbody.iterrows():
        detail = (f"{row.get('weight_lbs', '?')} lbs · "
                  f"{row.get('skeletal_muscle_mass_lbs', '?')} lbs SMM · "
                  f"{row.get('body_fat_pct', '?')}% BF")
        _add_event(events, row.get("date"), "Body comp", "InBody scan", detail)

# 4. N=1 experiments — start, end, control window
for e in data.nof1_experiments:
    title = e.get("title", "N=1 experiment")
    iv = e.get("intervention", {})
    _add_event(events, iv.get("start_date"), "N=1 experiment",
               f"Start: {title}", f"{iv.get('name', '')} · {iv.get('dose', '')}")
    if iv.get("end_date"):
        verdict = e.get("results", {}).get("verdict", e.get("status", ""))
        _add_event(events, iv.get("end_date"), "N=1 experiment",
                   f"End: {title}", f"verdict: {verdict}")

# 5. Action items — creation
if not data.action_items.empty:
    for _, row in data.action_items.iterrows():
        pri = (row.get("priority", "") or "").upper()
        _add_event(events, row.get("created_date"), "Action item",
                   f"[{pri}] {row.get('title', '')}",
                   f"status: {row.get('status', '')}")

# 6. Context notes
if not data.context_notes.empty:
    for _, row in data.context_notes.iterrows():
        _add_event(events, row.get("date"), "Context note",
                   row.get("category", "note"), row.get("note", ""))

events_df = pd.DataFrame(events)
if not events_df.empty:
    events_df = events_df.sort_values("date", ascending=False).reset_index(drop=True)

# ────────────────────────────────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────────────────────────────────
def _count(cat: str) -> int:
    return int((events_df["category"] == cat).sum()) if not events_df.empty else 0

total = len(events_df)
in_last_30 = int((events_df["date"] >= TODAY - pd.Timedelta(days=30)).sum()) if not events_df.empty else 0

kpis = [
    ("TOTAL EVENTS", f"{total}",                   "all-time", None),
    ("LAST 30 DAYS", f"{in_last_30}",              "recent",   None),
    ("BLOODWORK",    f"{_count('Bloodwork')}",      "draws",    None),
    ("PROTOCOL",     f"{_count('Protocol start')}", "starts",   None),
    ("N=1",          f"{_count('N=1 experiment')}", "events",   None),
    ("CONTEXT",      f"{_count('Context note')}",   "notes",    None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Filters
# ────────────────────────────────────────────────────────────────────────────
if events_df.empty:
    st.info("No events yet — once data is loaded, every dated entry across all "
            "sources will appear here.")
    st.stop()

with st.expander("🔎 Filter", expanded=True):
    fcols = st.columns([2, 2, 2])
    with fcols[0]:
        all_cats = sorted(events_df["category"].unique().tolist())
        selected_cats = st.multiselect(
            "Categories", options=all_cats, default=all_cats,
        )
    with fcols[1]:
        window = st.selectbox(
            "Time window",
            ["Last 30 days", "Last 90 days", "Last 12 months", "All time"],
            index=2,
        )
    with fcols[2]:
        search = st.text_input("Search title / detail")

window_days = {"Last 30 days": 30, "Last 90 days": 90,
               "Last 12 months": 365, "All time": None}[window]
filtered = events_df[events_df["category"].isin(selected_cats)].copy()
if window_days is not None:
    cutoff = TODAY - pd.Timedelta(days=window_days)
    filtered = filtered[filtered["date"] >= cutoff]
if search:
    s = search.lower()
    filtered = filtered[
        filtered["title"].str.lower().str.contains(s, na=False)
        | filtered["detail"].str.lower().str.contains(s, na=False)
    ]

st.caption(f"Showing **{len(filtered)}** of {len(events_df)} events")

# ────────────────────────────────────────────────────────────────────────────
# Tabs — gantt vs list
# ────────────────────────────────────────────────────────────────────────────
tab_gantt, tab_list, tab_table, tab_about = grouped_sections(
    ["📊 Lanes view", "🧾 Event list", "🗂 Table", "ℹ️ About"]
)

with tab_gantt:
    if filtered.empty:
        st.info("No events match the current filter.")
    else:
        # Group by category for lane chart
        cat_order = [c for c in CAT_COLORS.keys() if c in filtered["category"].unique()]
        fig = go.Figure()
        for cat in cat_order:
            sub = filtered[filtered["category"] == cat]
            fig.add_trace(go.Scatter(
                x=sub["date"], y=[cat] * len(sub),
                mode="markers",
                marker=dict(size=12, color=CAT_COLORS.get(cat, COLORS["chart_series"][0]),
                            line=dict(width=1, color="#1C1C1C")),
                name=cat,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{x|%b %d, %Y}<br>"
                    "%{customdata[1]}<extra></extra>"
                ),
                customdata=list(zip(sub["title"], sub["detail"])),
            ))
        fig.update_layout(
            yaxis=dict(categoryorder="array", categoryarray=cat_order[::-1]),
            xaxis=dict(title=""),
            showlegend=False,
            margin=dict(l=140, r=20, t=20, b=40),
        )
        apply_theme(fig, height=max(380, 64 * len(cat_order)))
        st.plotly_chart(fig, use_container_width=True)

with tab_list:
    if filtered.empty:
        st.info("No events match the current filter.")
    else:
        # Group by date — Notion-style
        for date, group in filtered.groupby(filtered["date"].dt.date, sort=False):
            st.markdown(
                f"<div style='color:#A0A0A0;font-size:0.85rem;margin-top:14px;"
                f"font-weight:600;letter-spacing:0.5px;'>"
                f"{pd.to_datetime(date).strftime('%b %d, %Y · %a')}</div>",
                unsafe_allow_html=True,
            )
            for _, row in group.iterrows():
                color = CAT_COLORS.get(row["category"], COLORS["chart_series"][0])
                st.markdown(
                    f'<div style="background:#1C1C1C;border-left:4px solid {color};'
                    f'padding:10px 14px;border-radius:6px;margin:6px 0;">'
                    f'<div style="display:flex;justify-content:space-between;">'
                    f'<strong style="color:#F0F0F0;">{row["title"]}</strong>'
                    f'<span style="background:{color}22;color:{color};padding:2px 8px;'
                    f'border-radius:4px;font-size:0.7rem;font-weight:600;">'
                    f'{row["category"].upper()}</span></div>'
                    f'<div style="color:#A0A0A0;font-size:0.85rem;margin-top:4px;">'
                    f'{row["detail"]}</div></div>',
                    unsafe_allow_html=True,
                )

with tab_table:
    show = filtered.copy()
    show["date"] = show["date"].dt.strftime("%Y-%m-%d")
    tl_show = show[["date", "category", "title", "detail"]]
    st.dataframe(tl_show, use_container_width=True, hide_index=True,
                 height=full_height(len(tl_show)))
    st.caption(f"{len(tl_show)} row(s)")
    st.download_button(
        "⬇ Download as CSV",
        data=show.to_csv(index=False),
        file_name=f"protocol_timeline_{TODAY.strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

with tab_about:
    st.markdown("""
**What this is.** A unified chronological feed of everything Protocōl knows about — every
lab draw, protocol start/end, body comp scan, N=1 experiment milestone, action item,
and context note.

**Why it matters.** A lot of health insight is about correlating events in time:
"my glucose drift started two weeks after I traveled" or "hsCRP normalized
right after BPC-157 began." This page is the single backbone for that kind of
narrative reasoning.

**Sources merged:**
- `bloodwork.csv` — one event per unique draw date
- `protocol.csv` — start + end events
- `inbody.csv` — every InBody scan
- `nof1_experiments.json` — start + end of each experiment
- `action_items.csv` — creation events
- `context_notes.csv` — every note (travel, illness, deload, etc.)
    """)
