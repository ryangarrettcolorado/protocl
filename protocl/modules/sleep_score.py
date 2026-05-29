"""Transparent sleep score formula — v3.0.

A single function `compute_sleep_score(night, baseline, sleep_need_min)`
returns a 0–100 composite score plus a fully-explained breakdown of its
four weighted components:

  Duration       40% — `100 * min(1, asleep_min / need_min)`
  Depth/Quality  30% — weighted blend of deep% (≥15% target) + REM% (≥20% target)
  HRV            20% — `100 * overnight_hrv / 28d_baseline_hrv`, clamped 0–100
  Consistency    10% — `100 - bed_time_stddev_min * 1.5`, clamped 0–100

Verdict thresholds:
  ready    ≥80   → train hard
  moderate 60–79 → train smart
  low      <60   → recovery day

Each component is rendered with its raw inputs so the UI's "see formula"
expander can show the user the math.
"""
from __future__ import annotations

from typing import Any


WEIGHTS = {
    "duration":     0.40,
    "depth_quality": 0.30,
    "hrv":          0.20,
    "consistency":  0.10,
}

VERDICT_READY    = "ready"
VERDICT_MODERATE = "moderate"
VERDICT_LOW      = "low"

TARGET_DEEP_PCT = 0.15
TARGET_REM_PCT  = 0.20


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _duration_score(asleep_min: float | None, need_min: float) -> float:
    if not asleep_min or asleep_min <= 0:
        return 0.0
    if not need_min or need_min <= 0:
        return 100.0
    return _clamp(100 * min(1.0, asleep_min / need_min))


def _depth_score(deep_min: float | None, rem_min: float | None,
                 total_asleep_min: float | None) -> tuple[float, float, float]:
    """Return (score, deep_pct, rem_pct).

    Each sub-component scored relative to its target (capped at 100). The
    blended score weights deep 0.6 and REM 0.4 (deep is more sensitive to
    recovery and supplements like CJC/Ipam).
    """
    if not total_asleep_min or total_asleep_min <= 0:
        return (0.0, 0.0, 0.0)
    deep_min = deep_min or 0.0
    rem_min  = rem_min  or 0.0
    deep_pct = deep_min / total_asleep_min
    rem_pct  = rem_min  / total_asleep_min
    deep_sub = _clamp(100 * (deep_pct / TARGET_DEEP_PCT))
    rem_sub  = _clamp(100 * (rem_pct  / TARGET_REM_PCT))
    score = 0.6 * deep_sub + 0.4 * rem_sub
    return (_clamp(score), deep_pct, rem_pct)


def _hrv_score(hrv: float | None, baseline: float | None) -> float:
    if not hrv or not baseline or baseline <= 0:
        return 50.0  # neutral when missing
    return _clamp(100 * (hrv / baseline))


def _consistency_score(bed_time_stddev_min: float | None) -> float:
    if bed_time_stddev_min is None:
        return 75.0  # neutral assumption when bed times absent
    return _clamp(100 - bed_time_stddev_min * 1.5)


def verdict(score: float) -> str:
    if score >= 80: return VERDICT_READY
    if score >= 60: return VERDICT_MODERATE
    return VERDICT_LOW


def compute_sleep_score(night: Any, baseline: dict[str, Any],
                        sleep_need_min: float = 480.0) -> dict[str, Any]:
    """Compute the v3.0 sleep score for one night.

    `night` is a SleepNight (or any object exposing the same attrs).
    `baseline` is the dict returned by `compute_baseline()`.
    """
    asleep    = getattr(night, "total_asleep_min", None)
    deep      = getattr(night, "deep_min", None)
    rem       = getattr(night, "rem_min", None)
    hrv       = getattr(night, "hrv_overnight_avg", None)
    bed_std   = baseline.get("bed_time_stddev_min") if baseline else None
    hrv_base  = baseline.get("hrv_baseline") if baseline else None

    dur_score = _duration_score(asleep, sleep_need_min)
    depth_s, deep_pct, rem_pct = _depth_score(deep, rem, asleep)
    hrv_s = _hrv_score(hrv, hrv_base)
    cons_s = _consistency_score(bed_std)

    composite = (
        WEIGHTS["duration"]      * dur_score +
        WEIGHTS["depth_quality"] * depth_s +
        WEIGHTS["hrv"]           * hrv_s +
        WEIGHTS["consistency"]   * cons_s
    )
    composite = round(_clamp(composite), 1)

    return {
        "score": composite,
        "components": {
            "duration": {
                "score": round(dur_score, 1),
                "weight": WEIGHTS["duration"],
                "value_min": int(asleep) if asleep else 0,
                "need_min": int(sleep_need_min),
            },
            "depth_quality": {
                "score": round(depth_s, 1),
                "weight": WEIGHTS["depth_quality"],
                "deep_pct": round(deep_pct, 3),
                "rem_pct": round(rem_pct, 3),
            },
            "hrv": {
                "score": round(hrv_s, 1),
                "weight": WEIGHTS["hrv"],
                "hrv": float(hrv) if hrv else None,
                "baseline": float(hrv_base) if hrv_base else None,
            },
            "consistency": {
                "score": round(cons_s, 1),
                "weight": WEIGHTS["consistency"],
                "bed_time_stddev_min": float(bed_std) if bed_std is not None else None,
            },
        },
        "verdict": verdict(composite),
    }
