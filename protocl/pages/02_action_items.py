"""Action Items — kanban view, due dates, complete/dismiss flow."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.data_loader import load_data, refresh_data, append_row, DATA_DIR, DEFAULT_USER
from modules.charts import COLORS, metric_card_html, full_height


from modules.theme import inject_css, grouped_sections
inject_css()
# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Action Items")
    st.caption("Open tasks, due dates, and quick completion flow")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
df = data.action_items.copy()

if df.empty:
    df = pd.DataFrame(columns=["id", "title", "priority", "category", "why_it_matters",
                                 "due_date", "related_metrics", "status",
                                 "source", "created_date"])

TODAY = pd.Timestamp("2026-05-25")
df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
df["days_to_due"] = (df["due_date"] - TODAY).dt.days

# ────────────────────────────────────────────────────────────────────────────
# Helpers — write status updates by rewriting the CSV
# ────────────────────────────────────────────────────────────────────────────
def update_status(item_id: str, new_status: str) -> None:
    """Rewrite the action items CSV with a status change for one item."""
    path = DATA_DIR / DEFAULT_USER / "action_items.csv"
    if not path.exists():
        return
    cur = pd.read_csv(path)
    cur.loc[cur["id"] == item_id, "status"] = new_status
    cur.to_csv(path, index=False)
    st.cache_data.clear()


# ────────────────────────────────────────────────────────────────────────────
# KPI cards
# ────────────────────────────────────────────────────────────────────────────
open_items = df[df["status"].isin(["open", "in_progress", "planned"])]
overdue = open_items[open_items["days_to_due"] < 0]
due_soon = open_items[(open_items["days_to_due"] >= 0) & (open_items["days_to_due"] <= 7)]
high_pri = open_items[open_items["priority"] == "high"]
completed_30d = df[
    (df["status"] == "completed") &
    (pd.to_datetime(df["created_date"], errors="coerce") >= TODAY - pd.Timedelta(days=30))
]

kpis = [
    ("OPEN", f"{len(open_items)}", "across all statuses", None),
    ("OVERDUE", f"{len(overdue)}", "past due date", len(overdue) == 0),
    ("DUE ≤7d", f"{len(due_soon)}", "this week", None),
    ("HIGH PRIORITY", f"{len(high_pri)}", "act first", len(high_pri) == 0),
    ("COMPLETED 30d", f"{len(completed_30d)}", "closed recently", None),
    ("TOTAL", f"{len(df)}", "all-time", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_board, tab_table, tab_add = grouped_sections(["📋 Board", "📊 Table", "➕ New Item"])

# ── Helpers ─────────────────────────────────────────────────────────────────
def priority_pill(priority: str) -> str:
    c = {"high": COLORS["danger"], "medium": COLORS["warning"],
         "low": COLORS["chart_series"][1]}.get(priority, COLORS["text_muted"])
    return (f'<span style="background:{c}22;color:{c};padding:2px 8px;'
            f'border-radius:4px;font-size:0.7rem;font-weight:600;">{priority.upper()}</span>')


def render_card(row: pd.Series) -> None:
    """Render a single action card with controls."""
    due = row["due_date"]
    days = row.get("days_to_due", 0)
    if pd.isna(due):
        due_str = "no due date"
        due_color = COLORS["text_muted"]
    elif days < 0:
        due_str = f"OVERDUE by {-int(days)}d"
        due_color = COLORS["danger"]
    elif days <= 7:
        due_str = f"due in {int(days)}d"
        due_color = COLORS["warning"]
    else:
        due_str = f"due {due.strftime('%b %d')}"
        due_color = COLORS["text_muted"]

    border = {"high": COLORS["danger"], "medium": COLORS["warning"],
              "low": COLORS["chart_series"][1]}.get(row.get("priority", "low"), COLORS["text_muted"])

    st.markdown(
        f'<div style="background:#1C1C1C;border-left:4px solid {border};'
        f'padding:14px 18px;border-radius:6px;margin-bottom:10px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
        f'<strong style="font-size:1.02rem;color:#F0F0F0;">{row["title"]}</strong>'
        f'{priority_pill(row.get("priority", "low"))}</div>'
        f'<div style="margin-top:6px;color:#A0A0A0;font-size:0.85rem;">'
        f'{row.get("why_it_matters", "")}</div>'
        f'<div style="margin-top:10px;display:flex;justify-content:space-between;'
        f'font-size:0.75rem;color:#A0A0A0;">'
        f'<span>{row.get("category", "")} · {row.get("source", "")}</span>'
        f'<span style="color:{due_color};font-weight:600;">{due_str}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Status controls
    btn_cols = st.columns(3)
    with btn_cols[0]:
        if st.button("✓ Complete", key=f"c_{row['id']}", use_container_width=True):
            update_status(row["id"], "completed")
            st.rerun()
    with btn_cols[1]:
        if st.button("→ In progress", key=f"p_{row['id']}", use_container_width=True):
            update_status(row["id"], "in_progress")
            st.rerun()
    with btn_cols[2]:
        if st.button("✕ Dismiss", key=f"d_{row['id']}", use_container_width=True):
            update_status(row["id"], "dismissed")
            st.rerun()


# ── Kanban-style board ──────────────────────────────────────────────────────
with tab_board:
    statuses = [
        ("open",        "🟡 Open"),
        ("in_progress", "🔵 In Progress"),
        ("planned",     "⚪ Planned"),
        ("completed",   "🟢 Completed"),
    ]
    cols = st.columns(len(statuses))
    for col, (status, label) in zip(cols, statuses):
        with col:
            subset = df[df["status"] == status].sort_values(
                ["priority", "due_date"],
                key=lambda c: c.map({"high": 0, "medium": 1, "low": 2}) if c.name == "priority" else c
            )
            st.markdown(f"### {label}")
            st.caption(f"{len(subset)} items")
            for _, row in subset.iterrows():
                render_card(row)

# ── Table view ──────────────────────────────────────────────────────────────
with tab_table:
    if df.empty:
        st.info("No action items yet — add one in the **New Item** tab.")
    else:
        show = df.copy()
        show["due_date"] = show["due_date"].dt.strftime("%Y-%m-%d")
        cols_show = ["id", "title", "priority", "category", "status",
                     "due_date", "related_metrics", "source", "created_date"]
        items_show = show[cols_show]
        st.dataframe(items_show, use_container_width=True, hide_index=True,
                     height=full_height(len(items_show)))
        st.caption(f"{len(items_show)} row(s)")

# ── New item ────────────────────────────────────────────────────────────────
with tab_add:
    st.subheader("Create New Action Item")
    with st.form("new_action"):
        title = st.text_input("Title")
        priority = st.selectbox("Priority", ["high", "medium", "low"], index=1)
        category = st.selectbox("Category",
                                 ["testing", "training", "protocol", "nutrition",
                                  "sleep", "supplement", "cardiovascular",
                                  "inflammation", "other"])
        why = st.text_area("Why it matters", height=80)
        due = st.date_input("Due date", value=(TODAY + pd.Timedelta(days=14)).date())
        related = st.text_input("Related metrics (comma-separated)")
        if st.form_submit_button("Save", use_container_width=True):
            new_id = f"act_{(len(df) + 1):03d}"
            append_row("action_items.csv", {
                "id": new_id,
                "title": title,
                "priority": priority,
                "category": category,
                "why_it_matters": why,
                "due_date": due.isoformat(),
                "related_metrics": related,
                "status": "open",
                "source": "manual",
                "created_date": TODAY.date().isoformat(),
            })
            st.success(f"{new_id} created.")
            st.rerun()
