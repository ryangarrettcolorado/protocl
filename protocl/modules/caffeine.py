"""Caffeine logging + half-life curve helpers for the Sleep page."""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import DATA_DIR, DEFAULT_USER


CAFFEINE_FILE = "caffeine_log.csv"
CAFFEINE_COLS = ["timestamp", "amount_mg", "source"]
HALF_LIFE_HRS = 5.5

# Quick-log presets (label, mg, emoji)
PRESETS = [
    ("☕ 1 cup coffee", 95,   "coffee"),
    ("☕☕ 2 cups",      190,  "coffee_2x"),
    ("🥤 Pre-workout", 200,  "preworkout"),
    ("🍵 Tea",          47,  "tea"),
]


def caffeine_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / CAFFEINE_FILE


def load_caffeine_log(user_id: str = DEFAULT_USER) -> pd.DataFrame:
    p = caffeine_path(user_id)
    if not p.exists():
        return pd.DataFrame(columns=CAFFEINE_COLS)
    df = pd.read_csv(p)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def log_caffeine(amount_mg: float, source: str = "manual",
                 when: datetime | None = None, user_id: str = DEFAULT_USER) -> None:
    p = caffeine_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = (when or datetime.now()).isoformat(timespec="minutes")
    row = pd.DataFrame([{"timestamp": ts, "amount_mg": float(amount_mg), "source": source}])
    if p.exists():
        row.to_csv(p, mode="a", header=False, index=False)
    else:
        row.to_csv(p, mode="w", header=True, index=False)


def remaining_mg(entries: pd.DataFrame, at_time: datetime) -> float:
    """Estimated caffeine still active at `at_time`, summing decay across logs."""
    if entries is None or entries.empty:
        return 0.0
    total = 0.0
    for _, row in entries.iterrows():
        ts = row.get("timestamp")
        if pd.isna(ts):
            continue
        hrs = (at_time - pd.Timestamp(ts).to_pydatetime()).total_seconds() / 3600.0
        if hrs < 0:
            continue
        try:
            mg = float(row.get("amount_mg") or 0)
        except (TypeError, ValueError):
            continue
        total += mg * (0.5 ** (hrs / HALF_LIFE_HRS))
    return round(total, 1)


def decay_curve(entries: pd.DataFrame, start: datetime, hours: int = 18) -> pd.DataFrame:
    """Return a DataFrame of (time, mg_active) sampled every 30 min from `start`."""
    rows = []
    for offset_min in range(0, hours * 60 + 1, 30):
        t = start + timedelta(minutes=offset_min)
        rows.append({"time": t, "mg_active": remaining_mg(entries, t)})
    return pd.DataFrame(rows)


def recommend_cutoff(target_bedtime: datetime, target_residual_mg: float = 25.0) -> datetime:
    """Last time you can drink coffee (95mg) and still be ≤target_residual_mg at bedtime."""
    if target_bedtime is None:
        return target_bedtime
    # Solve 95 * 0.5^(hrs/5.5) ≤ target -> hrs ≥ 5.5 * log2(95/target)
    if target_residual_mg <= 0 or target_residual_mg >= 95:
        return target_bedtime
    hours_needed = HALF_LIFE_HRS * math.log2(95.0 / target_residual_mg)
    return target_bedtime - timedelta(hours=hours_needed)
