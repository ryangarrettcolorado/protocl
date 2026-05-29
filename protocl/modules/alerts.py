"""Alerts engine — v3.1.

Implements:
  - Alert dataclass (with deterministic id)
  - evaluate_all_alerts() running every individual evaluator
  - state persistence (active + snoozed) in alerts_state.json
  - history append (alerts_history.csv)

Each evaluate_* helper is small and pure: it takes loaded data and returns
either an Alert or None. Tests target the individual evaluators.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import DATA_DIR, DEFAULT_USER, load_data


CATEGORY_BLOODWORK_CADENCE = "bloodwork_cadence"
CATEGORY_BIOMARKER         = "biomarker"
CATEGORY_SUPPLEMENT        = "supplement"
CATEGORY_PROTOCOL          = "protocol"
CATEGORY_FRESHNESS         = "freshness"
CATEGORY_SLEEP             = "sleep"
CATEGORY_CALENDAR          = "calendar"

SEVERITY_CRITICAL = "critical"
SEVERITY_WARNING  = "warning"
SEVERITY_INFO     = "info"


def _stable_id(category: str, key: str, fired_date: str) -> str:
    h = hashlib.sha256(f"{category}|{key}|{fired_date}".encode()).hexdigest()
    return h[:16]


@dataclass
class Alert:
    id: str
    category: str
    severity: str
    title: str
    body: str
    action: str | None = None
    action_url: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    fired_at: str = ""
    snoozed_until: str | None = None
    dismissed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now().date().isoformat()


def _alert(category: str, key: str, severity: str, title: str, body: str,
           action: str | None = None, action_url: str | None = None,
           evidence: dict | None = None) -> Alert:
    return Alert(
        id=_stable_id(category, key, _today()),
        category=category,
        severity=severity,
        title=title,
        body=body,
        action=action,
        action_url=action_url,
        evidence=evidence or {},
        fired_at=_now_iso(),
    )


# ──────────────────────────────────────────────────────────────────────────
# Per-evaluator helpers
# ──────────────────────────────────────────────────────────────────────────

# Bloodwork cadence
def evaluate_q1_panel_due(target_date: str | None = None) -> Alert | None:
    """Fires 14 days before configured Q1 target date."""
    today = datetime.now().date()
    target = target_date or f"{today.year}-01-15"
    try:
        t = datetime.strptime(target, "%Y-%m-%d").date()
    except ValueError:
        return None
    if t < today:
        # Roll to next year
        t = t.replace(year=today.year + 1)
    days_to = (t - today).days
    if 0 <= days_to <= 14:
        return _alert(
            CATEGORY_BLOODWORK_CADENCE, f"q1_panel_{t.year}",
            SEVERITY_WARNING,
            "Q1 Insurance Comprehensive Panel due",
            f"Your Q1 comprehensive panel is scheduled in {days_to} days ({t.isoformat()}).",
            action="Schedule lab visit",
            evidence={"target_date": t.isoformat(), "days_until": days_to},
        )
    return None


def evaluate_quarterly_panel_due(protocol_df: pd.DataFrame | None = None) -> Alert | None:
    """Quarterly Marek/Anabolic panel (every ~90d)."""
    today = datetime.now().date()
    # If we have bloodwork history, use last draw + 90; otherwise pin to quarter
    bw = load_data().bloodwork
    last_draw = None
    if not bw.empty:
        try:
            last_draw = pd.Timestamp(bw["date"].max()).date()
        except Exception:
            last_draw = None
    if last_draw:
        next_due = last_draw + timedelta(days=90)
        days_to = (next_due - today).days
        if 0 <= days_to <= 14:
            return _alert(
                CATEGORY_BLOODWORK_CADENCE, f"quarterly_{next_due.isoformat()}",
                SEVERITY_WARNING,
                "Quarterly anabolic panel due",
                f"Quarterly panel due {next_due.isoformat()} ({days_to} days).",
                action="Order Marek panel",
                evidence={"last_draw": last_draw.isoformat(), "next_due": next_due.isoformat()},
            )
    return None


def evaluate_anavar_mid_cycle(protocol_df: pd.DataFrame | None = None) -> Alert | None:
    """Fires at day 21 of any active Anavar cycle."""
    df = protocol_df
    if df is None or df.empty:
        df = load_data().protocol
    if df.empty:
        return None
    today = datetime.now().date()
    anavar = df[df["name"].str.contains("Anavar|Oxandrolone", case=False, na=False)]
    if anavar.empty:
        return None
    for _, row in anavar.iterrows():
        try:
            start = pd.Timestamp(row.get("start_date")).date()
        except Exception:
            continue
        cycle_status = (row.get("cycle_status") or "").lower()
        if cycle_status != "active":
            continue
        days_in = (today - start).days
        if 19 <= days_in <= 23:
            return _alert(
                CATEGORY_PROTOCOL, f"anavar_mid_cycle_{start.isoformat()}",
                SEVERITY_WARNING,
                "Anavar mid-cycle ALT/AST check due",
                f"Day {days_in} of Anavar cycle — schedule a liver panel.",
                action="Order ALT/AST",
                evidence={"cycle_start": start.isoformat(), "days_in": days_in},
            )
    return None


def evaluate_lpa_once_ever() -> Alert | None:
    bw = load_data().bloodwork
    if bw.empty:
        return None
    col_candidates = [c for c in bw.columns if "lp_a" in c.lower() or "lpa" == c.lower()]
    has_lpa = False
    for c in col_candidates:
        if bw[c].notna().any():
            has_lpa = True
            break
    if not has_lpa and "biomarker" in bw.columns:
        has_lpa = (bw["biomarker"].astype(str).str.contains("lp_a", case=False, na=False)).any()
    if not has_lpa:
        return _alert(
            CATEGORY_BLOODWORK_CADENCE, "lpa_never_drawn",
            SEVERITY_INFO,
            "Lp(a) never measured",
            "Lp(a) is a genetic risk marker — recommend a one-time draw.",
            action="Order Lp(a)",
        )
    return None


# Biomarker thresholds
_BIOMARKER_RULES: list[tuple[str, str, float, float | None, str]] = [
    # (biomarker_key, label, warn, crit, unit)
    ("hct_pct",             "Hct",     52, 54,   "%"),
    ("hematocrit_pct",      "Hct",     52, 54,   "%"),
    ("alt_u_l",             "ALT",     40, 60,   "U/L"),
    ("ast_u_l",             "AST",     40, 60,   "U/L"),
    ("apob_mg_dl",          "ApoB",    80, 100,  "mg/dL"),
    ("hscrp_mg_l",          "hs-CRP",  2,  5,    "mg/L"),
]


def _latest_value(bw: pd.DataFrame, key: str) -> float | None:
    """Wide-form (col=biomarker) or long-form (biomarker/value) fallback."""
    if bw.empty:
        return None
    if key in bw.columns:
        s = bw.sort_values("date")[key].dropna()
        if not s.empty:
            try: return float(s.iloc[-1])
            except (TypeError, ValueError): return None
    if "biomarker" in bw.columns and "value" in bw.columns:
        rows = bw[bw["biomarker"] == key]
        if not rows.empty:
            try: return float(rows.sort_values("date").iloc[-1]["value"])
            except (TypeError, ValueError): return None
    return None


def evaluate_biomarker_thresholds(bloodwork: pd.DataFrame | None = None,
                                   overrides: dict | None = None) -> list[Alert]:
    bw = bloodwork if bloodwork is not None else load_data().bloodwork
    overrides = overrides or {}
    alerts: list[Alert] = []
    seen_labels: set[str] = set()
    for key, label, warn, crit, unit in _BIOMARKER_RULES:
        if label in seen_labels:
            continue
        v = _latest_value(bw, key)
        if v is None:
            continue
        seen_labels.add(label)
        warn = float(overrides.get(f"{key}_warn", warn))
        crit_eff = float(overrides.get(f"{key}_crit", crit)) if crit is not None else None
        if crit_eff is not None and v >= crit_eff:
            alerts.append(_alert(
                CATEGORY_BIOMARKER, f"{key}_critical",
                SEVERITY_CRITICAL,
                f"{label} critical: {v:.1f} {unit}",
                f"{label} = {v:.1f} {unit} exceeds critical threshold ({crit_eff} {unit}).",
                action=f"Review {label} with physician",
                evidence={"value": v, "threshold_warn": warn, "threshold_crit": crit_eff},
            ))
        elif v >= warn:
            alerts.append(_alert(
                CATEGORY_BIOMARKER, f"{key}_warning",
                SEVERITY_WARNING,
                f"{label} elevated: {v:.1f} {unit}",
                f"{label} = {v:.1f} {unit} above warning threshold ({warn} {unit}).",
                evidence={"value": v, "threshold_warn": warn},
            ))
    # E2 — bidirectional
    e2 = _latest_value(bw, "estradiol_sensitive_pg_ml") or _latest_value(bw, "e2_sensitive_pg_ml")
    if e2 is not None:
        if e2 < 20 or e2 > 40:
            alerts.append(_alert(
                CATEGORY_BIOMARKER, f"e2_oor_{e2:.1f}",
                SEVERITY_WARNING,
                f"Sensitive E2 out of range: {e2:.1f} pg/mL",
                "Sensitive E2 outside the 20–40 pg/mL therapeutic window.",
                evidence={"value": e2, "range": "20-40 pg/mL"},
            ))
    return alerts


# Supplement reorders
def evaluate_supplement_reorders(inventory_df: pd.DataFrame | None = None) -> list[Alert]:
    df = inventory_df
    if df is None:
        df = _load_inventory()
    if df.empty:
        return []
    today = datetime.now().date()
    alerts: list[Alert] = []
    for _, row in df.iterrows():
        try:
            qty = float(row.get("quantity_remaining") or 0)
            dose = float(row.get("daily_dose") or 0)
        except (TypeError, ValueError):
            continue
        if dose <= 0:
            continue
        days_remaining = qty / dose
        # Decay since last purchase
        last_purchase = row.get("last_purchase_date")
        if pd.notna(last_purchase):
            try:
                lp = pd.Timestamp(last_purchase).date()
                last_qty = float(row.get("last_purchase_quantity") or qty)
                days_since = (today - lp).days
                est_remaining = max(0.0, last_qty - days_since * dose)
                days_remaining = est_remaining / dose if dose > 0 else 0
            except Exception:
                pass

        name = row.get("supplement_name") or "Supplement"
        url = row.get("reorder_url") or None
        sev = None
        if days_remaining <= 2:
            sev = SEVERITY_CRITICAL
        elif days_remaining <= 7:
            sev = SEVERITY_WARNING
        elif days_remaining <= 14:
            sev = SEVERITY_INFO
        if sev:
            alerts.append(_alert(
                CATEGORY_SUPPLEMENT, f"reorder_{name}",
                sev,
                f"Reorder {name}",
                f"~{days_remaining:.0f} days remaining at current dose.",
                action="Mark as reordered",
                action_url=url,
                evidence={"days_remaining": round(days_remaining, 1)},
            ))
    return alerts


def _load_inventory() -> pd.DataFrame:
    p = DATA_DIR / DEFAULT_USER / "supplement_inventory.csv"
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
        return df
    except Exception:
        return pd.DataFrame()


# Data freshness
def evaluate_data_freshness() -> list[Alert]:
    today = datetime.now().date()
    data = load_data()
    alerts: list[Alert] = []
    # HealthKit sync — use wearables most recent date
    if not data.wearables.empty:
        try:
            last_w = pd.Timestamp(data.wearables["date"].max()).date()
            days = (today - last_w).days
            if days >= 3:
                alerts.append(_alert(
                    CATEGORY_FRESHNESS, "healthkit_stale",
                    SEVERITY_WARNING,
                    "HealthKit not syncing",
                    f"No wearables data for {days} days. Check Apple Health export.",
                    evidence={"days_stale": days, "last": last_w.isoformat()},
                ))
        except Exception:
            pass
    # Strava — use training table
    if not data.training.empty:
        try:
            last_t = pd.Timestamp(data.training["date"].max()).date()
            days = (today - last_t).days
            if days >= 7:
                alerts.append(_alert(
                    CATEGORY_FRESHNESS, "strava_stale",
                    SEVERITY_INFO,
                    "Strava — no activity in {} days".format(days),
                    f"No Strava activities for {days} days.",
                    evidence={"days_stale": days},
                ))
        except Exception:
            pass
    # Bloodwork freshness
    if not data.bloodwork.empty:
        try:
            last_b = pd.Timestamp(data.bloodwork["date"].max()).date()
            days = (today - last_b).days
            if days > 110:
                alerts.append(_alert(
                    CATEGORY_FRESHNESS, "bloodwork_stale",
                    SEVERITY_WARNING,
                    "Bloodwork >110 days old",
                    f"Last draw {days} days ago.",
                    evidence={"days_stale": days},
                ))
        except Exception:
            pass
    return alerts


# Sleep-specific
def evaluate_sleep_alerts() -> list[Alert]:
    """Sleep-specific alerts using A1–A8 outputs."""
    try:
        from modules.sleep_data import load_sleep_nights, compute_baseline
        from modules.sleep_need import compute_sleep_need
    except Exception:
        return []

    nights = load_sleep_nights(window_days=30)
    if not nights:
        return []
    baseline = compute_baseline(nights, days=28)
    need = compute_sleep_need(nights=nights,
                               wearables=load_data().wearables,
                               training=load_data().training,
                               bloodwork=load_data().bloodwork)
    need_min = need["sleep_need_min"]

    alerts: list[Alert] = []
    # 5-day rolling debt
    last5 = [n for n in nights[-5:] if n.total_asleep_min]
    if len(last5) >= 3:
        total = sum(n.total_asleep_min for n in last5)
        target = need_min * len(last5)
        if total < target * 0.85:
            debt_min = target - total
            alerts.append(_alert(
                CATEGORY_SLEEP, "rolling_sleep_debt",
                SEVERITY_WARNING,
                "Sleep debt accumulating",
                f"Last {len(last5)} nights: {debt_min/60:.1f}h debt — consider rest day.",
                evidence={"debt_min": int(debt_min)},
            ))
    # HRV trending down >2σ
    if baseline.get("hrv_baseline"):
        hrvs = [n.hrv_overnight_avg for n in nights[-28:] if n.hrv_overnight_avg]
        if len(hrvs) >= 14:
            mean = sum(hrvs) / len(hrvs)
            std = (sum((x - mean) ** 2 for x in hrvs) / len(hrvs)) ** 0.5
            last7 = [n.hrv_overnight_avg for n in nights[-7:] if n.hrv_overnight_avg]
            if last7 and std > 0:
                avg7 = sum(last7) / len(last7)
                z = (avg7 - mean) / std
                if z < -2.0:
                    alerts.append(_alert(
                        CATEGORY_SLEEP, "hrv_trend_down",
                        SEVERITY_WARNING,
                        "HRV trending sharply down",
                        f"7d HRV {avg7:.0f} ms is {z:.1f}σ below 28d baseline.",
                        evidence={"z": round(z, 2)},
                    ))
    return alerts


# Protocol-tied scheduling
def evaluate_anavar_end_planning(protocol_df: pd.DataFrame | None = None) -> Alert | None:
    df = protocol_df if protocol_df is not None else load_data().protocol
    if df.empty:
        return None
    today = datetime.now().date()
    anavar = df[df["name"].str.contains("Anavar|Oxandrolone", case=False, na=False)]
    if anavar.empty:
        return None
    for _, row in anavar.iterrows():
        end = row.get("end_date")
        if pd.isna(end):
            continue
        try:
            ed = pd.Timestamp(end).date()
        except Exception:
            continue
        days_to = (ed - today).days
        if 0 <= days_to <= 14:
            return _alert(
                CATEGORY_PROTOCOL, f"anavar_end_planning_{ed.isoformat()}",
                SEVERITY_INFO,
                "Anavar cycle planning consult",
                f"Cycle ends in {days_to} days — schedule post-cycle review.",
                action="Schedule consult",
                evidence={"cycle_end": ed.isoformat()},
            )
    return None


# Calendar-aware (placeholder — no live gcal connector in v3.1)
def evaluate_travel_detected(calendar_events: list[dict] | None = None) -> Alert | None:
    if not calendar_events:
        return None
    today = datetime.now().date()
    keywords = ("flight", "travel", "trip", "airport")
    for ev in calendar_events:
        title = (ev.get("summary") or "").lower()
        try:
            d = pd.Timestamp(ev.get("start") or ev.get("date")).date()
        except Exception:
            continue
        days = (d - today).days
        if 3 <= days <= 14 and any(k in title for k in keywords):
            return _alert(
                CATEGORY_CALENDAR, f"travel_{d.isoformat()}",
                SEVERITY_INFO,
                "Travel detected",
                f"Travel in {days} days — jet lag protocol available (v3 future release).",
                evidence={"date": d.isoformat()},
            )
    return None


# ──────────────────────────────────────────────────────────────────────────
# Orchestrator + state
# ──────────────────────────────────────────────────────────────────────────

STATE_FILE = "alerts_state.json"
HISTORY_FILE = "alerts_history.csv"


def _state_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / STATE_FILE


def _history_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / HISTORY_FILE


def load_state(user_id: str = DEFAULT_USER) -> dict[str, Any]:
    p = _state_path(user_id)
    if not p.exists():
        return {"snoozed": {}, "dismissed": {}, "last_critical_sent": {}}
    try:
        with p.open() as f:
            return json.load(f)
    except Exception:
        return {"snoozed": {}, "dismissed": {}, "last_critical_sent": {}}


def save_state(state: dict[str, Any], user_id: str = DEFAULT_USER) -> None:
    p = _state_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(state, f, indent=2)


def snooze_alert(alert_id: str, days: int = 1, user_id: str = DEFAULT_USER) -> None:
    state = load_state(user_id)
    until = (datetime.now() + timedelta(days=days)).isoformat()
    state.setdefault("snoozed", {})[alert_id] = until
    save_state(state, user_id)


def dismiss_alert(alert_id: str, user_id: str = DEFAULT_USER) -> None:
    state = load_state(user_id)
    state.setdefault("dismissed", {})[alert_id] = _now_iso()
    save_state(state, user_id)
    _append_history(alert_id, "dismissed", user_id)


def _append_history(alert_id: str, action: str, user_id: str = DEFAULT_USER) -> None:
    p = _history_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    write_header = not p.exists()
    with p.open("a", newline="") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "alert_id", "action"])
        w.writerow([_now_iso(), alert_id, action])


def _apply_state(alerts: list[Alert], state: dict[str, Any]) -> list[Alert]:
    """Drop alerts that are dismissed or snoozed-not-expired."""
    out = []
    snoozed = state.get("snoozed", {}) or {}
    dismissed = state.get("dismissed", {}) or {}
    now = datetime.now()
    for a in alerts:
        if a.id in dismissed:
            continue
        sn = snoozed.get(a.id)
        if sn:
            try:
                if datetime.fromisoformat(sn) > now:
                    continue
            except Exception:
                pass
        out.append(a)
    return out


def evaluate_all_alerts(user_id: str = DEFAULT_USER,
                        overrides: dict | None = None,
                        category_toggles: dict | None = None) -> list[Alert]:
    """Run every individual evaluator. Returns the active (non-snoozed/dismissed) list."""
    toggles = category_toggles or {}
    alerts: list[Alert] = []

    def _on(cat: str) -> bool:
        return toggles.get(cat, True)

    bw = load_data(user_id).bloodwork
    proto = load_data(user_id).protocol

    if _on(CATEGORY_BLOODWORK_CADENCE):
        for fn in (evaluate_q1_panel_due,
                   evaluate_quarterly_panel_due,
                   evaluate_lpa_once_ever):
            try:
                r = fn() if fn != evaluate_quarterly_panel_due else fn(proto)
                if r: alerts.append(r)
            except Exception:
                continue
    if _on(CATEGORY_PROTOCOL):
        for fn in (evaluate_anavar_mid_cycle, evaluate_anavar_end_planning):
            try:
                r = fn(proto)
                if r: alerts.append(r)
            except Exception:
                continue
    if _on(CATEGORY_BIOMARKER):
        try:
            alerts.extend(evaluate_biomarker_thresholds(bw, overrides))
        except Exception:
            pass
    if _on(CATEGORY_SUPPLEMENT):
        try:
            alerts.extend(evaluate_supplement_reorders())
        except Exception:
            pass
    if _on(CATEGORY_FRESHNESS):
        try:
            alerts.extend(evaluate_data_freshness())
        except Exception:
            pass
    if _on(CATEGORY_SLEEP):
        try:
            alerts.extend(evaluate_sleep_alerts())
        except Exception:
            pass

    state = load_state(user_id)
    return _apply_state(alerts, state)


def group_by_severity(alerts: list[Alert]) -> dict[str, list[Alert]]:
    order = [SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO]
    grouped: dict[str, list[Alert]] = {s: [] for s in order}
    for a in alerts:
        grouped.setdefault(a.severity, []).append(a)
    return grouped
