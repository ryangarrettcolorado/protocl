"""Sleep data model + loaders for v3.0 Sleep Coaching.

The wearables CSV is the canonical source (Apple HealthKit ingest). This
module normalizes a row into a SleepNight dict with deterministic field
names and computes a 28-day baseline for HRV / RHR / sleep need.

Stage data is famously incomplete; loaders return partial records rather
than dropping nights with missing fields.

Also provides read/write helpers for the subjective sleep_journal.csv.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import math
import pandas as pd

from modules.data_loader import DATA_DIR, DEFAULT_USER, load_data


JOURNAL_FILE = "sleep_journal.csv"
JOURNAL_COLS = ["date", "mood_1_5", "fatigue_1_5", "soreness_1_5", "notes"]


@dataclass
class SleepNight:
    date: str                       # ISO YYYY-MM-DD
    in_bed_start: str | None = None
    in_bed_end: str | None = None
    asleep_start: str | None = None
    asleep_end: str | None = None
    total_in_bed_min: float | None = None
    total_asleep_min: float | None = None
    time_to_fall_asleep_min: float | None = None
    awake_min: float | None = None
    light_min: float | None = None
    deep_min: float | None = None
    rem_min: float | None = None
    hrv_overnight_avg: float | None = None
    resting_hr: float | None = None
    respiratory_rate: float | None = None
    sleep_consistency_score: float | None = None
    # Fields that are missing from the underlying data
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _f(val: Any) -> float | None:
    """Coerce a pandas cell to float or None (NaN-safe)."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _from_wearables_row(row: pd.Series) -> SleepNight:
    """Map a wearables.csv row to a SleepNight, filling stage fields from
    the duration / deep / rem columns. Light is derived as
    asleep_min - deep_min - rem_min when possible.
    """
    date_val = row.get("date")
    iso = pd.Timestamp(date_val).date().isoformat() if pd.notna(date_val) else None

    total_hrs = _f(row.get("sleep_duration_hrs"))
    deep_hrs  = _f(row.get("sleep_deep_hrs"))
    rem_hrs   = _f(row.get("sleep_rem_hrs"))

    total_min = total_hrs * 60 if total_hrs is not None else None
    deep_min  = deep_hrs  * 60 if deep_hrs  is not None else None
    rem_min   = rem_hrs   * 60 if rem_hrs   is not None else None

    light_min = None
    if total_min is not None and deep_min is not None and rem_min is not None:
        light_min = max(0.0, total_min - deep_min - rem_min)

    night = SleepNight(
        date=iso or "",
        total_asleep_min=total_min,
        total_in_bed_min=total_min,  # AHK doesn't separate; conservative equality
        deep_min=deep_min,
        rem_min=rem_min,
        light_min=light_min,
        awake_min=None,
        hrv_overnight_avg=_f(row.get("hrv_sdnn_ms")),
        resting_hr=_f(row.get("resting_hr_bpm")),
        respiratory_rate=_f(row.get("respiratory_rate_brpm")),
        sleep_consistency_score=_f(row.get("sleep_consistency_pct")),
    )

    missing = []
    if night.total_asleep_min is None: missing.append("total_asleep_min")
    if night.deep_min is None:         missing.append("deep_min")
    if night.rem_min is None:          missing.append("rem_min")
    if night.hrv_overnight_avg is None: missing.append("hrv_overnight_avg")
    if night.resting_hr is None:        missing.append("resting_hr")
    night.missing = missing
    return night


def load_sleep_nights(window_days: int = 90, user_id: str = DEFAULT_USER) -> list[SleepNight]:
    """Pull recent sleep nights from the wearables backend.

    Returns at most `window_days` of the most recent nights. Nights with no
    sleep data at all are still returned as partial records (just flagged).
    """
    data = load_data(user_id)
    w = data.wearables
    if w.empty or "date" not in w.columns:
        return []
    w = w.sort_values("date").tail(int(window_days))
    return [_from_wearables_row(r) for _, r in w.iterrows()]


def get_latest_night(user_id: str = DEFAULT_USER) -> SleepNight | None:
    """Return the most recent SleepNight that has any sleep data."""
    nights = load_sleep_nights(window_days=14, user_id=user_id)
    for n in reversed(nights):
        if n.total_asleep_min and n.total_asleep_min > 30:
            return n
    return nights[-1] if nights else None


def compute_baseline(nights: list[SleepNight], days: int = 28) -> dict[str, float | None]:
    """Compute the 28-day baseline for HRV / RHR / asleep min.

    Returns dict with keys: hrv_baseline, rhr_baseline, asleep_baseline_min,
    bed_time_stddev_min, sample_size.
    """
    recent = nights[-days:] if nights else []
    hrv = [n.hrv_overnight_avg for n in recent if n.hrv_overnight_avg]
    rhr = [n.resting_hr for n in recent if n.resting_hr]
    asleep = [n.total_asleep_min for n in recent if n.total_asleep_min and n.total_asleep_min > 30]

    def _mean(xs):
        return sum(xs) / len(xs) if xs else None

    return {
        "hrv_baseline": _mean(hrv),
        "rhr_baseline": _mean(rhr),
        "asleep_baseline_min": _mean(asleep),
        # bed_time variance — wearables.csv has no bed start; surface 0 here
        # and let the consistency computation use whatever signal is available.
        "bed_time_stddev_min": 0.0,
        "sample_size": len(asleep),
    }


# ──────────────────────────────────────────────────────────────────────────
# Subjective journal helpers
# ──────────────────────────────────────────────────────────────────────────

def journal_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / JOURNAL_FILE


def load_journal(user_id: str = DEFAULT_USER) -> pd.DataFrame:
    p = journal_path(user_id)
    if not p.exists():
        return pd.DataFrame(columns=JOURNAL_COLS)
    try:
        df = pd.read_csv(p)
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df
    except Exception:
        return pd.DataFrame(columns=JOURNAL_COLS)


def write_journal_entry(date_iso: str, mood: int, fatigue: int, soreness: int,
                        notes: str = "", user_id: str = DEFAULT_USER) -> None:
    p = journal_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    row = pd.DataFrame([{
        "date": date_iso,
        "mood_1_5": int(mood),
        "fatigue_1_5": int(fatigue),
        "soreness_1_5": int(soreness),
        "notes": (notes or "").replace("\n", " ").strip(),
    }])
    if p.exists():
        existing = load_journal(user_id)
        # Replace today's row if it already exists
        existing["date_iso"] = pd.to_datetime(existing["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        existing = existing[existing["date_iso"] != date_iso].drop(columns=["date_iso"])
        out = pd.concat([existing, row], ignore_index=True)
        out.to_csv(p, index=False)
    else:
        row.to_csv(p, index=False)


def has_journal_entry_today(today_iso: str, user_id: str = DEFAULT_USER) -> bool:
    df = load_journal(user_id)
    if df.empty:
        return False
    iso = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return bool((iso == today_iso).any())
