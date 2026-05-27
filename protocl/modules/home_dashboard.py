"""Home dashboard composition logic — the seven-row command center.

Each ``render_row_*`` function renders one row and is dispatched by
``render_home`` based on the user's row visibility + order preferences.

Where the v1.5 spec references static files that don't yet exist in v1
(``risks.csv``, ``recommendations.csv``, ``timeline.csv``, ``next_visit.json``),
this module derives the equivalent data on the fly from the existing
CSVs/JSON so the dashboard works against the live v1 data backend.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from modules.biomarker_aliases import display_name
from modules.bioage import latest_phenoage
from modules.charts import (
    COLORS,
    apply_theme,
    metric_card_html,
    status_badge_html,
    status_label,
)
from modules.data_loader import (
    DATA_DIR,
    DEFAULT_USER,
    HealthData,
    latest_bloodwork_draw,
    load_data,
    previous_bloodwork_draw,
)
from modules.nav import page_link
from modules.preferences import (
    home_row_order,
    home_rows_visible,
    pinned_biomarkers,
    profile,
)
from modules.reference_ranges import load_reference


# Demo / dev "today" — matches v1 convention used elsewhere in the codebase.
TODAY = pd.Timestamp("2026-05-25")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _safe(value: Any, fmt: str = "{:.0f}", placeholder: str = "—") -> str:
    """Format a value with graceful fallback."""
    try:
        if value is None:
            return placeholder
        if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
            return placeholder
        return fmt.format(value)
    except (ValueError, TypeError):
        return placeholder


def _birth_date(prefs: dict | None = None) -> pd.Timestamp:
    p = profile(prefs)
    dob = p.get("date_of_birth") or "1983-11-14"
    try:
        return pd.Timestamp(dob)
    except Exception:
        return pd.Timestamp("1983-11-14")


def _days_ago(ts: pd.Timestamp | None) -> int | None:
    if ts is None or pd.isna(ts):
        return None
    return int((TODAY - pd.Timestamp(ts)).days)


def _human_days_ago(days: int | None) -> str:
    """Render a day-count as a human-readable months + days string.

    Uses a 30-day month approximation. Examples:
      237 → "7mo 27d ago"; 45 → "1mo 15d ago"; 30 → "1mo ago"; 20 → "20d ago".
    """
    if days is None:
        return "—"
    days = int(days)
    if days < 0:
        return "today"
    if days < 30:
        return f"{days}d ago"
    months, rem = divmod(days, 30)
    if rem == 0:
        return f"{months}mo ago"
    return f"{months}mo {rem}d ago"


def _next_visit() -> dict | None:
    """Load ``data/<user>/next_visit.json`` if it exists."""
    p = DATA_DIR / DEFAULT_USER / "next_visit.json"
    if not p.exists():
        return None
    try:
        with p.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


# ────────────────────────────────────────────────────────────────────────────
# Row 1 — Status strip (8 KPI tiles)
# ────────────────────────────────────────────────────────────────────────────

def _bioage_tile(data: HealthData, birth_date: pd.Timestamp) -> tuple[str, str, str, bool | None]:
    """Return (label, value, delta, positive)."""
    chrono = (TODAY - birth_date).days / 365.25
    res = latest_phenoage(data.bloodwork, birth_date) if not data.bloodwork.empty else None
    if res is None or res.pheno_age is None:
        return ("Biological Age", "—", f"chrono {chrono:.1f}y", None)
    delta = res.pheno_age - chrono
    positive = delta < 0  # younger biological age is "good"
    return (
        "Biological Age",
        f"{res.pheno_age:.1f}y",
        f"{delta:+.1f}y vs chrono ({chrono:.1f}y)",
        positive,
    )


def _last_bloodwork_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    bw = data.bloodwork
    if bw.empty:
        return ("Last Bloodwork", "—", "no data", None)
    last = pd.Timestamp(bw["date"].max())
    days = _days_ago(last) or 0
    n_draws = bw["date"].nunique()
    return ("Last Bloodwork", _human_days_ago(days), f"{n_draws} draws on file", days < 180)


def _vo2_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    w = data.wearables
    if w.empty or "vo2_max_ml_kg_min" not in w.columns:
        return ("VO₂ max", "—", "no data", None)
    latest = w.sort_values("date")["vo2_max_ml_kg_min"].dropna()
    if latest.empty:
        return ("VO₂ max", "—", "no data", None)
    v = float(latest.iloc[-1])
    # Coarse age-graded percentile bands for a ~40s male.
    if v >= 53: band = "Elite (95th+)"
    elif v >= 48: band = "Superior (80th)"
    elif v >= 42: band = "Above avg (60th)"
    elif v >= 36: band = "Average"
    else: band = "Below avg"
    return ("VO₂ max", f"{v:.1f}", band, v >= 42)


def _bf_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    ib = data.inbody
    if ib.empty:
        return ("Body Fat %", "—", "no DEXA", None)
    ib = ib.sort_values("date")
    bf = float(ib["body_fat_pct"].iloc[-1])
    if len(ib) >= 2:
        prev = float(ib["body_fat_pct"].iloc[-2])
        d = bf - prev
        delta = f"{d:+.1f}% vs last scan"
        positive = d <= 0
    else:
        delta = "first scan"
        positive = None
    return ("Body Fat %", f"{bf:.1f}%", delta, positive)


def _sleep_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    w = data.wearables
    if w.empty or "sleep_duration_hrs" not in w.columns:
        return ("Sleep (7d)", "—", "no data", None)
    w = w.sort_values("date")
    last_7 = w["sleep_duration_hrs"].dropna().tail(7)
    last_30 = w["sleep_duration_hrs"].dropna().tail(30)
    if last_7.empty:
        return ("Sleep (7d)", "—", "no data", None)
    avg_7 = last_7.mean()
    avg_30 = last_30.mean() if not last_30.empty else avg_7
    d = avg_7 - avg_30
    return ("Sleep (7d)", f"{avg_7:.1f}h", f"{d:+.2f}h vs 30d", d >= 0)


def _hrv_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    w = data.wearables
    if w.empty or "hrv_sdnn_ms" not in w.columns:
        return ("HRV (7d)", "—", "no data", None)
    w = w.sort_values("date")
    last_7 = w["hrv_sdnn_ms"].dropna().tail(7)
    last_30 = w["hrv_sdnn_ms"].dropna().tail(30)
    if last_7.empty:
        return ("HRV (7d)", "—", "no data", None)
    avg_7 = last_7.mean()
    avg_30 = last_30.mean() if not last_30.empty else avg_7
    d = avg_7 - avg_30
    return ("HRV (7d)", f"{avg_7:.0f}ms", f"{d:+.1f}ms vs 30d", d >= 0)


def _rhr_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    w = data.wearables
    if w.empty or "resting_hr_bpm" not in w.columns:
        return ("Resting HR (7d)", "—", "no data", None)
    w = w.sort_values("date")
    last_7 = w["resting_hr_bpm"].dropna().tail(7)
    last_30 = w["resting_hr_bpm"].dropna().tail(30)
    if last_7.empty:
        return ("Resting HR (7d)", "—", "no data", None)
    avg_7 = last_7.mean()
    avg_30 = last_30.mean() if not last_30.empty else avg_7
    d = avg_7 - avg_30
    return ("Resting HR (7d)", f"{avg_7:.0f} bpm", f"{d:+.1f} vs 30d", d <= 0)


def _tir_tile(data: HealthData) -> tuple[str, str, str, bool | None]:
    cgm = data.cgm_readings
    if cgm.empty:
        return ("Glucose TIR (14d)", "—", "no CGM", None)
    cgm = cgm.sort_values("datetime")
    cutoff_14 = TODAY - pd.Timedelta(days=14)
    cutoff_60 = TODAY - pd.Timedelta(days=60)
    last_14 = cgm[cgm["datetime"] >= cutoff_14]
    last_60 = cgm[cgm["datetime"] >= cutoff_60]
    if last_14.empty:
        last_14 = cgm.tail(2016)  # ~7 days fallback
    tir_14 = ((last_14["glucose_mg_dl"] >= 70) & (last_14["glucose_mg_dl"] <= 140)).mean()
    tir_60 = ((last_60["glucose_mg_dl"] >= 70) & (last_60["glucose_mg_dl"] <= 140)).mean() if not last_60.empty else tir_14
    d = (tir_14 - tir_60) * 100
    return ("Glucose TIR (14d)", f"{tir_14 * 100:.0f}%", f"{d:+.1f}pp vs 60d", d >= 0)


def render_row_status(data: HealthData, prefs: dict) -> None:
    """Row 1 — eight KPI tiles."""
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### At a glance")

    birth = _birth_date(prefs)
    tiles = [
        _bioage_tile(data, birth),
        _last_bloodwork_tile(data),
        _vo2_tile(data),
        _bf_tile(data),
        _sleep_tile(data),
        _hrv_tile(data),
        _rhr_tile(data),
        _tir_tile(data),
    ]

    # 4-per-row x 2 rows reads well on most screens.
    for row_start in (0, 4):
        cols = st.columns(4)
        for col, (label, value, delta, positive) in zip(cols, tiles[row_start:row_start + 4]):
            with col:
                st.markdown(
                    metric_card_html(label, value, delta, positive),
                    unsafe_allow_html=True,
                )
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 2 — Active alerts banner (derived from latest bloodwork off-target)
# ────────────────────────────────────────────────────────────────────────────

def _derive_active_risks(data: HealthData, ref: dict) -> list[dict]:
    """Compute active risks from latest bloodwork draw + simple wearable triggers."""
    risks: list[dict] = []
    latest = latest_bloodwork_draw(data.bloodwork)
    if not latest.empty:
        for _, row in latest.iterrows():
            r = ref.get(row["biomarker_canonical"])
            if not r:
                continue
            s = status_label(row["value"], r.get("optimal_low"), r.get("optimal_high"),
                             r.get("lab_low"), r.get("lab_high"))
            if s in ("Risk", "Monitor"):
                risks.append({
                    "id": row["biomarker_canonical"],
                    "label": display_name(row["biomarker_canonical"]),
                    "severity": "high" if s == "Risk" else "monitor",
                    "value": row["value"],
                    "unit": row.get("unit", ""),
                })

    # Hematocrit watch is a TRT-specific perennial.
    risks.sort(key=lambda r: 0 if r["severity"] == "high" else 1)
    return risks


def render_row_alerts(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### Active alerts")

    ref = load_reference()
    risks = _derive_active_risks(data, ref)
    if not risks:
        st.markdown(
            '<div class="alert-banner-nominal">All systems nominal — no active risks.</div>',
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)
        return

    chips = []
    for r in risks[:12]:
        cls = "alert-chip-high" if r["severity"] == "high" else "alert-chip-monitor"
        chips.append(f'<span class="{cls}">{r["label"]} · {r["value"]} {r["unit"]}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)

    # Deep link to the full Risks page.
    col_link, _ = st.columns([1, 4])
    with col_link:
        page_link("risks_alerts", label="Open Risks & Alerts →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 3 — What needs my attention today (3 cards)
# ────────────────────────────────────────────────────────────────────────────

def _update_action_status(item_id: str, new_status: str) -> None:
    path = DATA_DIR / DEFAULT_USER / "action_items.csv"
    if not path.exists():
        return
    cur = pd.read_csv(path)
    cur.loc[cur["id"] == item_id, "status"] = new_status
    cur.to_csv(path, index=False)
    st.cache_data.clear()


def _render_attention_action_items(data: HealthData) -> None:
    st.markdown("**Open action items**")
    df = data.action_items.copy()
    if df.empty:
        st.caption("No action items yet.")
        return
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce")
    df["_pri"] = df["priority"].map({"high": 0, "medium": 1, "low": 2}).fillna(3)
    open_items = (
        df[df["status"].isin(["open", "in_progress", "planned"])]
        .sort_values(["_pri", "due_date"])
    )
    if open_items.empty:
        st.success("All clear — no open items.")
        return
    for _, row in open_items.head(3).iterrows():
        pri = row.get("priority", "low")
        pri_color = {"high": COLORS["danger"], "medium": COLORS["warning"],
                     "low": COLORS["chart_series"][1]}.get(pri, COLORS["text_muted"])
        due = row.get("due_date")
        if pd.notna(due):
            days = (due - TODAY).days
            if days < 0:
                due_text = f"<span style='color:{COLORS['danger']}'>overdue {-int(days)}d</span>"
            elif days <= 7:
                due_text = f"<span style='color:{COLORS['warning']}'>due {int(days)}d</span>"
            else:
                due_text = f"due {due.strftime('%b %d')}"
        else:
            due_text = "no due date"

        st.markdown(
            f'<div style="background:#1C1C1C;border-left:3px solid {pri_color};'
            f'padding:8px 12px;border-radius:4px;margin-bottom:6px;">'
            f'<div style="font-size:0.95rem;color:#F0F0F0">{row["title"]}</div>'
            f'<div style="font-size:0.78rem;color:#A0A0A0;margin-top:2px;">'
            f'{pri.upper()} · {due_text}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("✓ Complete", key=f"home_complete_{row['id']}", use_container_width=True):
            _update_action_status(row["id"], "completed")
            st.rerun()


def _render_attention_nof1(data: HealthData) -> None:
    st.markdown("**Active N=1 experiments**")
    exps = [e for e in data.nof1_experiments if e.get("status") == "active"]
    if not exps:
        st.caption("No active experiments — design one on the N=1 page.")
        return
    for e in exps[:3]:
        iv = e.get("intervention", {}) or {}
        outcome = (e.get("primary_outcome") or {}).get("metric", "—")
        end = e.get("end_date") or e.get("planned_end_date")
        days_remaining = "—"
        if end:
            try:
                d = (pd.Timestamp(end) - TODAY).days
                days_remaining = f"{d}d left" if d > 0 else "ending"
            except Exception:
                pass
        st.markdown(
            f'<div class="rec-card">'
            f'<div class="rec-card-title">🧪 {e.get("title", "Experiment")}</div>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.82rem;">'
            f'{iv.get("name", "—")} · outcome: {outcome} · {days_remaining}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_attention_protocol(data: HealthData) -> None:
    st.markdown("**Protocol attention**")
    prot = data.protocol.copy()
    if prot.empty:
        st.caption("No protocol items.")
        return
    flags = []
    active = prot[prot["end_date"].isna()] if "end_date" in prot.columns else prot
    # Cycle ending within 7 days (peptide/hormone with a planned end_date set)
    if "end_date" in prot.columns:
        ending = prot[prot["end_date"].notna()].copy()
        ending["end_date"] = pd.to_datetime(ending["end_date"], errors="coerce")
        ending = ending[(ending["end_date"] >= TODAY) &
                        (ending["end_date"] <= TODAY + pd.Timedelta(days=7))]
        for _, row in ending.iterrows():
            flags.append((row["name"], f"cycle ends {row['end_date'].strftime('%b %d')}"))

    # Adherence drift — anything < 80%.
    if "adherence_pct" in active.columns:
        for _, row in active[active["adherence_pct"] < 80].iterrows():
            flags.append((row["name"], f"adherence {int(row['adherence_pct'])}%"))

    if not flags:
        st.success("Protocol on-track.")
        return
    for name, note in flags[:4]:
        st.markdown(
            f'<div style="background:#1C1C1C;border-left:3px solid {COLORS["warning"]};'
            f'padding:8px 12px;border-radius:4px;margin-bottom:6px;">'
            f'<div style="font-size:0.95rem;color:#F0F0F0">{name}</div>'
            f'<div style="font-size:0.78rem;color:#A0A0A0;margin-top:2px;">{note}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_row_attention(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### What needs my attention today")
    c1, c2, c3 = st.columns(3)
    with c1: _render_attention_action_items(data)
    with c2: _render_attention_nof1(data)
    with c3: _render_attention_protocol(data)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 4 — Trends (3 chart columns)
# ────────────────────────────────────────────────────────────────────────────

def _pinned_biomarker_chart(data: HealthData, prefs: dict) -> go.Figure | None:
    pins = pinned_biomarkers(prefs)
    if not pins or data.bloodwork.empty:
        return None
    cutoff = TODAY - pd.Timedelta(days=90)
    bw = data.bloodwork.copy()
    bw = bw[bw["date"] >= cutoff]
    if bw.empty:
        # Fall back to all-time so the chart isn't empty for older data.
        bw = data.bloodwork.copy()
    ref = load_reference()
    fig = go.Figure()
    for i, bm in enumerate(pins):
        sub = bw[bw["biomarker_canonical"] == bm].sort_values("date")
        if sub.empty:
            continue
        r = ref.get(bm, {})
        target = r.get("optimal_high") or 1
        fig.add_trace(go.Scatter(
            x=sub["date"], y=sub["value"] / target * 100,
            mode="lines+markers",
            name=display_name(bm),
            line=dict(color=COLORS["chart_series"][i % len(COLORS["chart_series"])], width=2),
            marker=dict(size=6),
            hovertemplate=f"<b>{display_name(bm)}</b><br>%{{x|%b %Y}}<br>%{{customdata}}<extra></extra>",
            customdata=sub["value"].astype(str) + " " + sub.get("unit", pd.Series([""] * len(sub))).fillna(""),
        ))
    if not fig.data:
        return None
    apply_theme(fig, height=260)
    fig.update_layout(
        yaxis_title="% of optimal target",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
        margin=dict(t=30, b=30, l=30, r=10),
    )
    return fig


def _body_comp_chart(data: HealthData) -> go.Figure | None:
    ib = data.inbody.copy()
    if ib.empty:
        return None
    ib = ib.sort_values("date").tail(24)  # ~12 months at 2/mo cadence
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ib["date"], y=ib["body_fat_pct"],
        mode="lines+markers", name="Body Fat %",
        line=dict(color=COLORS["warning"], width=2), yaxis="y",
        hovertemplate="%{x|%b %Y}<br>BF %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=ib["date"], y=ib["lean_mass_lbs"],
        mode="lines+markers", name="Lean Mass (lbs)",
        line=dict(color=COLORS["gold"], width=2), yaxis="y2",
        hovertemplate="%{x|%b %Y}<br>Lean %{y:.1f} lbs<extra></extra>",
    ))
    apply_theme(fig, height=260)
    fig.update_layout(
        yaxis=dict(title="Body Fat %", gridcolor=COLORS["steel_light"]),
        yaxis2=dict(title="Lean Mass (lbs)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
        margin=dict(t=30, b=30, l=30, r=30),
    )
    return fig


def _hrv_sleep_chart(data: HealthData) -> go.Figure | None:
    w = data.wearables.copy()
    if w.empty:
        return None
    cutoff = TODAY - pd.Timedelta(days=90)
    w = w[w["date"] >= cutoff].sort_values("date")
    if w.empty:
        w = data.wearables.sort_values("date").tail(90)
    fig = go.Figure()
    if "hrv_sdnn_ms" in w.columns:
        fig.add_trace(go.Scatter(
            x=w["date"], y=w["hrv_sdnn_ms"],
            mode="lines", name="HRV (SDNN ms)",
            line=dict(color=COLORS["gold"], width=2),
            hovertemplate="%{x|%b %d}<br>HRV %{y:.0f} ms<extra></extra>",
        ))
    if "sleep_duration_hrs" in w.columns:
        fig.add_trace(go.Scatter(
            x=w["date"], y=w["sleep_duration_hrs"],
            mode="lines", name="Sleep (hrs)",
            line=dict(color=COLORS["chart_series"][1], width=1.5, dash="dot"),
            yaxis="y2",
            hovertemplate="%{x|%b %d}<br>Sleep %{y:.1f} h<extra></extra>",
        ))
    apply_theme(fig, height=260)
    fig.update_layout(
        yaxis=dict(title="HRV (ms)", gridcolor=COLORS["steel_light"]),
        yaxis2=dict(title="Sleep (hrs)", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, font=dict(size=10)),
        margin=dict(t=30, b=30, l=30, r=30),
    )
    return fig


def render_row_trends(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### Trends")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Pinned biomarkers (90d)**")
        fig = _pinned_biomarker_chart(data, prefs)
        if fig is None:
            st.caption("Pin biomarkers from Settings → Home Dashboard Layout.")
        else:
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.markdown("**Body composition**")
        fig = _body_comp_chart(data)
        if fig is None:
            st.caption("No DEXA / InBody data yet.")
        else:
            st.plotly_chart(fig, use_container_width=True)
    with c3:
        st.markdown("**HRV + Sleep (90d)**")
        fig = _hrv_sleep_chart(data)
        if fig is None:
            st.caption("No wearables data yet.")
        else:
            st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 5 — What changed recently (timeline)
# ────────────────────────────────────────────────────────────────────────────

def _derive_timeline_events(data: HealthData, limit: int = 5) -> list[dict]:
    events: list[dict] = []

    if not data.bloodwork.empty:
        latest_date = data.bloodwork["date"].max()
        n_markers = len(data.bloodwork[data.bloodwork["date"] == latest_date])
        events.append({
            "date": latest_date, "icon": "🩸",
            "text": f"Bloodwork drawn — {n_markers} markers updated",
            "page": "bloodwork",
        })

    if not data.protocol.empty:
        prot = data.protocol.copy()
        prot["start_date"] = pd.to_datetime(prot["start_date"], errors="coerce")
        recent_starts = prot.sort_values("start_date", ascending=False).head(3)
        for _, row in recent_starts.iterrows():
            if pd.isna(row["start_date"]):
                continue
            events.append({
                "date": row["start_date"], "icon": "⚗️",
                "text": f"Started {row['name']} {row.get('dose','')} {row.get('unit','')}".strip(),
                "page": "protocol",
            })

    if not data.inbody.empty:
        ib = data.inbody.sort_values("date")
        latest = ib.iloc[-1]
        if len(ib) >= 2:
            prev = ib.iloc[-2]
            d = latest["body_fat_pct"] - prev["body_fat_pct"]
            text = f"DEXA scan — body fat {('↑' if d > 0 else '↓')}{abs(d):.1f}%"
        else:
            text = f"DEXA scan — body fat {latest['body_fat_pct']:.1f}%"
        events.append({
            "date": latest["date"], "icon": "📐",
            "text": text, "page": "body_composition",
        })

    # N=1 experiment milestones
    for e in data.nof1_experiments:
        if e.get("status") == "active":
            start = e.get("start_date")
            if start:
                events.append({
                    "date": pd.Timestamp(start), "icon": "🧪",
                    "text": f"N=1 '{e.get('title','experiment')}' — in progress",
                    "page": "nof1_experiments",
                })

    events.sort(key=lambda x: x["date"], reverse=True)
    return events[:limit]


def render_row_changes(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### What changed recently")
    events = _derive_timeline_events(data, limit=5)
    if not events:
        st.caption("No recent events to summarize.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    for e in events:
        date_str = pd.Timestamp(e["date"]).strftime("%b %d")
        st.markdown(
            f'<div class="timeline-event-row">'
            f'<span class="timeline-event-icon">{e["icon"]}</span>'
            f'<span class="timeline-event-date">{date_str}</span>'
            f'<span class="timeline-event-text">{e["text"]}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    col_link, _ = st.columns([1, 4])
    with col_link:
        page_link("timeline", label="Full Timeline →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 6 — Recommendations (top 3 derived)
# ────────────────────────────────────────────────────────────────────────────

def _derive_recommendations(data: HealthData) -> list[dict]:
    """Lightweight rule-based recommendations until a real LLM/static source ships."""
    ref = load_reference()
    recs: list[dict] = []
    latest = latest_bloodwork_draw(data.bloodwork)

    if not latest.empty:
        hct = latest[latest["biomarker_canonical"] == "hematocrit_pct"]
        if not hct.empty and hct["value"].iloc[0] > 48:
            recs.append({
                "title": "Monitor hematocrit on TRT",
                "evidence": f"HCT at {hct['value'].iloc[0]:.1f}% — trending up.",
                "priority": "high",
            })
        vd = latest[latest["biomarker_canonical"] == "vitamin_d_ng_ml"]
        if not vd.empty and vd["value"].iloc[0] < 60:
            recs.append({
                "title": "Push Vitamin D into 60–80 ng/mL",
                "evidence": f"Vitamin D at {vd['value'].iloc[0]:.0f} ng/mL — below optimal.",
                "priority": "medium",
            })
        for bm_key, threshold, title, why in [
            ("apob_mg_dl", 80, "Lower ApoB toward 60–80 mg/dL",
             "ApoB is the better cardiovascular risk marker than LDL-C."),
            ("hba1c_pct", 5.4, "Tighten glycemic control",
             "HbA1c above 5.4% reflects rising average glucose."),
        ]:
            row = latest[latest["biomarker_canonical"] == bm_key]
            if not row.empty and row["value"].iloc[0] > threshold:
                recs.append({
                    "title": title,
                    "evidence": f"{display_name(bm_key)} at {row['value'].iloc[0]} — {why}",
                    "priority": "medium",
                })

    if not data.training.empty:
        recent = data.training[data.training["date"] >= TODAY - pd.Timedelta(days=7)]
        z2 = recent["zone2_min"].sum() if "zone2_min" in recent else 0
        if z2 < 150:
            recs.append({
                "title": "Hit 150 Zone 2 minutes this week",
                "evidence": f"{int(z2)} Z2 min this week vs 150-min target.",
                "priority": "medium",
            })

    return recs[:3]


def render_row_recommendations(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### Recommendations")
    recs = _derive_recommendations(data)
    if not recs:
        st.success("No high-priority recommendations active. Your data is on-trend.")
        st.markdown('</div>', unsafe_allow_html=True)
        return
    cols = st.columns(min(3, len(recs)))
    for col, rec in zip(cols, recs):
        with col:
            pri_color = {"high": COLORS["danger"], "medium": COLORS["warning"],
                         "low": COLORS["text_muted"]}.get(rec["priority"], COLORS["text_muted"])
            st.markdown(
                f'<div class="rec-card">'
                f'<div class="rec-card-title">{rec["title"]}</div>'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.85rem">{rec["evidence"]}</div>'
                f'<div style="margin-top:6px;color:{pri_color};font-size:0.72rem;font-weight:600;">'
                f'{rec["priority"].upper()} PRIORITY</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    col_link, _ = st.columns([1, 4])
    with col_link:
        page_link("recommendations", label="View all →", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Row 7 — Clinician handoff
# ────────────────────────────────────────────────────────────────────────────

def render_row_clinician(data: HealthData, prefs: dict) -> None:
    st.markdown('<div class="home-row">', unsafe_allow_html=True)
    st.markdown("#### Clinician handoff")
    visit = _next_visit()
    if visit and visit.get("date"):
        try:
            visit_date = pd.Timestamp(visit["date"])
            days = (visit_date - TODAY).days
            last_summary = visit.get("last_summary_generated")
            last_text = ""
            if last_summary:
                try:
                    ls = pd.Timestamp(last_summary)
                    last_text = f"Last summary generated {(TODAY - ls).days} days ago."
                except Exception:
                    pass
            st.markdown(
                f'<div class="rec-card">'
                f'<div class="rec-card-title">Next physician visit in {days} days '
                f'({visit_date.strftime("%b %d, %Y")})</div>'
                f'<div style="color:{COLORS["text_muted"]};font-size:0.9rem;">{last_text}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            st.caption("Set a next-visit date in Settings to enable handoff prompts.")
    else:
        st.markdown(
            f'<div class="rec-card">'
            f'<div class="rec-card-title">No upcoming visit on file</div>'
            f'<div style="color:{COLORS["text_muted"]};font-size:0.9rem;">'
            f'Set a next-visit date to get handoff prompts here.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    col_link, _ = st.columns([1, 4])
    with col_link:
        page_link("clinician_summary", label="Generate / view summary →",
                  use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────────────────
# Orchestrator
# ────────────────────────────────────────────────────────────────────────────

ROW_RENDERERS: dict[str, Callable[[HealthData, dict], None]] = {
    "status":          render_row_status,
    "alerts":          render_row_alerts,
    "attention":       render_row_attention,
    "trends":          render_row_trends,
    "changes":         render_row_changes,
    "recommendations": render_row_recommendations,
    "clinician":       render_row_clinician,
}


def render_home(prefs: dict | None = None) -> None:
    """Render the full Home dashboard respecting visibility + order from prefs."""
    data = load_data()
    visible = set(home_rows_visible(prefs))
    order = home_row_order(prefs)

    for row in order:
        if row not in visible:
            continue
        renderer = ROW_RENDERERS.get(row)
        if renderer is None:
            continue
        renderer(data, prefs or {})
