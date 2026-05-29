"""Personalized sleep need calculator.

Starts from generic 8h (480 min) and adds adjustments based on training
load, HRV trend, illness/inflammation, travel, and recent sleep debt.
Returns the final sleep_need_min plus the list of adjustments applied
so the UI can explain "your need is 540 min — +45 from yesterday's
ride, +30 from travel tomorrow".
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd


BASE_NEED_MIN = 480  # 8h baseline

ADJUSTMENTS = {
    "training_strain":      45,   # yesterday hard ride
    "training_strain_low":  30,   # yesterday moderate
    "hrv_trend_down":       30,   # 7d HRV trending down >5%
    "illness":              60,   # hsCRP elevated or RHR up >7 bpm
    "travel":               30,   # flight / hotel keywords on calendar
    "sleep_debt_carryover": 45,   # 2-night cumulative <85% of need
}


def _yesterday(today: pd.Timestamp | date) -> pd.Timestamp:
    return pd.Timestamp(today) - pd.Timedelta(days=1)


def _has_recent_training_strain(training: pd.DataFrame, today: pd.Timestamp) -> tuple[bool, str]:
    """Return (is_strain, magnitude_label). magnitude in {"high","moderate","none"}."""
    if training is None or training.empty or "date" not in training.columns:
        return (False, "none")
    yest = _yesterday(today).date()
    df = training.copy()
    df["d"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    row = df[df["d"] == yest]
    if row.empty:
        return (False, "none")
    # heuristic columns
    moving_min = float(row.get("moving_time_min", pd.Series([0])).iloc[0] or 0)
    hr_avg = float(row.get("avg_heart_rate", pd.Series([0])).iloc[0] or 0)
    if moving_min >= 90 or hr_avg >= 150:
        return (True, "high")
    if moving_min >= 45 or hr_avg >= 130:
        return (True, "moderate")
    return (False, "none")


def _hrv_trending_down(wearables: pd.DataFrame, today: pd.Timestamp) -> bool:
    if wearables is None or wearables.empty or "hrv_sdnn_ms" not in wearables.columns:
        return False
    df = wearables.copy()
    df["d"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["d", "hrv_sdnn_ms"]).sort_values("d")
    if len(df) < 14:
        return False
    last_7 = df.tail(7)["hrv_sdnn_ms"].mean()
    last_28 = df.tail(28)["hrv_sdnn_ms"].mean()
    if not last_28 or pd.isna(last_28):
        return False
    return (last_7 - last_28) / last_28 < -0.05


def _illness_flag(bloodwork: pd.DataFrame, wearables: pd.DataFrame,
                  today: pd.Timestamp) -> bool:
    # hs-CRP elevated (latest > 2.0 mg/L)
    if bloodwork is not None and not bloodwork.empty:
        crp_col = "hscrp_mg_l" if "hscrp_mg_l" in bloodwork.columns else None
        if crp_col is None and "biomarker" in bloodwork.columns:
            crp_rows = bloodwork[bloodwork["biomarker"] == "hscrp_mg_l"]
            if not crp_rows.empty and "value" in crp_rows.columns:
                try:
                    if float(crp_rows.sort_values("date").iloc[-1]["value"]) > 2.0:
                        return True
                except Exception:
                    pass
        elif crp_col:
            try:
                v = float(bloodwork.sort_values("date").iloc[-1][crp_col])
                if v > 2.0:
                    return True
            except Exception:
                pass
    # RHR up >7 bpm for 2+ days vs 28d baseline
    if wearables is not None and not wearables.empty and "resting_hr_bpm" in wearables.columns:
        df = wearables.copy()
        df["d"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["d", "resting_hr_bpm"]).sort_values("d")
        if len(df) >= 28:
            baseline = df.tail(28)["resting_hr_bpm"].mean()
            last_2 = df.tail(2)["resting_hr_bpm"]
            if len(last_2) == 2 and (last_2 - baseline).min() > 7:
                return True
    return False


def _travel_flag(calendar_events: list[dict], today: pd.Timestamp) -> bool:
    """Calendar events list (best-effort). If unavailable, returns False."""
    if not calendar_events:
        return False
    keywords = ("flight", "travel", "hotel", "airport")
    window_start = today.date()
    window_end = (today + pd.Timedelta(days=1)).date()
    for ev in calendar_events:
        title = (ev.get("summary") or ev.get("title") or "").lower()
        try:
            d = pd.Timestamp(ev.get("start") or ev.get("date")).date()
        except Exception:
            continue
        if window_start <= d <= window_end and any(k in title for k in keywords):
            return True
    return False


def _sleep_debt_carryover(nights: list, base_need: int = BASE_NEED_MIN) -> bool:
    """True if last 2 nights cumulative asleep < 85% of (2 * base_need)."""
    if not nights or len(nights) < 2:
        return False
    last_two = [n for n in nights[-2:] if getattr(n, "total_asleep_min", None)]
    if len(last_two) < 2:
        return False
    total = sum(n.total_asleep_min for n in last_two)
    return total < (2 * base_need) * 0.85


def compute_sleep_need(
    nights: list,
    wearables: pd.DataFrame | None = None,
    training: pd.DataFrame | None = None,
    bloodwork: pd.DataFrame | None = None,
    calendar_events: list[dict] | None = None,
    today: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Return dict with `sleep_need_min`, `base_min`, `adjustments` (list of
    dicts each `{label, minutes, reason}`).
    """
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.now().normalize()
    base = BASE_NEED_MIN
    adjustments: list[dict[str, Any]] = []

    strain, magnitude = _has_recent_training_strain(training if training is not None else pd.DataFrame(), today)
    if strain:
        amt = ADJUSTMENTS["training_strain"] if magnitude == "high" else ADJUSTMENTS["training_strain_low"]
        adjustments.append({"label": f"Yesterday training ({magnitude})", "minutes": amt,
                            "reason": "Recovery cost from training load"})

    if _hrv_trending_down(wearables if wearables is not None else pd.DataFrame(), today):
        adjustments.append({"label": "7d HRV trending down", "minutes": ADJUSTMENTS["hrv_trend_down"],
                            "reason": "Autonomic recovery deficit"})

    if _illness_flag(bloodwork if bloodwork is not None else pd.DataFrame(),
                     wearables if wearables is not None else pd.DataFrame(), today):
        adjustments.append({"label": "Illness / inflammation signal", "minutes": ADJUSTMENTS["illness"],
                            "reason": "Elevated CRP or RHR — extra recovery"})

    if _travel_flag(calendar_events or [], today):
        adjustments.append({"label": "Travel detected", "minutes": ADJUSTMENTS["travel"],
                            "reason": "Jet lag / disrupted routine buffer"})

    if _sleep_debt_carryover(nights, base):
        adjustments.append({"label": "Carryover sleep debt", "minutes": ADJUSTMENTS["sleep_debt_carryover"],
                            "reason": "Last 2 nights <85% of need"})

    total = base + sum(a["minutes"] for a in adjustments)
    return {
        "sleep_need_min": total,
        "base_min": base,
        "adjustments": adjustments,
    }
