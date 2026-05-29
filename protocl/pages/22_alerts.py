"""🚨 Alerts — full list page with snooze/dismiss + history."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.alerts import (
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
    SEVERITY_INFO,
    dismiss_alert,
    evaluate_all_alerts,
    group_by_severity,
    snooze_alert,
)
from modules.charts import COLORS
from modules.data_loader import DATA_DIR, DEFAULT_USER
from modules.preferences import load_preferences
from modules.theme import inject_css


inject_css()


SEV_COLORS = {
    SEVERITY_CRITICAL: "#EF5350",
    SEVERITY_WARNING:  "#FFD54F",
    SEVERITY_INFO:     "#4FC3F7",
}
SEV_LABELS = {
    SEVERITY_CRITICAL: "Critical",
    SEVERITY_WARNING:  "Warning",
    SEVERITY_INFO:     "Info",
}


def _alert_overrides() -> dict:
    prefs = load_preferences()
    return ((prefs.get("alerts") or {}).get("thresholds") or {})


def _category_toggles() -> dict:
    prefs = load_preferences()
    cats = (prefs.get("alerts") or {}).get("categories") or {}
    return cats


st.title("🚨 Alerts")
st.caption("Today's watchlist · history · evidence")

tab_active, tab_history = st.tabs(["Active", "History (30d)"])

with tab_active:
    alerts = evaluate_all_alerts(overrides=_alert_overrides(),
                                  category_toggles=_category_toggles())
    grouped = group_by_severity(alerts)

    total = sum(len(v) for v in grouped.values())
    if total == 0:
        st.success("✓ All systems clear — no active alerts.")
    else:
        st.caption(f"{total} active alert{'s' if total != 1 else ''}")

    for sev in (SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO):
        items = grouped.get(sev, [])
        if not items:
            continue
        st.markdown(f"### {SEV_LABELS[sev]}")
        for a in items:
            color = SEV_COLORS[sev]
            st.markdown(
                f"""<div style='border-left:4px solid {color};padding:10px 14px;
                margin:8px 0;background:{COLORS["steel_mid"]};border-radius:6px;'>
                <strong>{a.title}</strong><br>
                <span style='color:{COLORS["text_muted"]};font-size:0.9rem;'>{a.body}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
            with col1:
                if st.button("Snooze 1d", key=f"sn1_{a.id}"):
                    snooze_alert(a.id, days=1)
                    st.rerun()
            with col2:
                if st.button("Snooze 1w", key=f"sn7_{a.id}"):
                    snooze_alert(a.id, days=7)
                    st.rerun()
            with col3:
                if st.button("Dismiss", key=f"dis_{a.id}"):
                    dismiss_alert(a.id)
                    st.rerun()
            with col4:
                if a.evidence:
                    with st.expander("Evidence"):
                        st.json(a.evidence)

with tab_history:
    p = DATA_DIR / DEFAULT_USER / "alerts_history.csv"
    if not p.exists():
        st.caption("No alert history yet.")
    else:
        try:
            hist = pd.read_csv(p)
            hist["timestamp"] = pd.to_datetime(hist["timestamp"], errors="coerce")
            cutoff = datetime.now() - timedelta(days=30)
            recent = hist[hist["timestamp"] >= cutoff].sort_values("timestamp", ascending=False)
            if recent.empty:
                st.caption("No alert actions in the last 30 days.")
            else:
                st.dataframe(recent, use_container_width=True)
        except Exception as e:
            st.error(f"Failed to read history: {e}")
