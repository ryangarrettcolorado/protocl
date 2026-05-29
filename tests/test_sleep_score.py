"""Tests for sleep score formula — edge cases + happy path."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make protocl/ importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

from modules.sleep_data import SleepNight  # noqa: E402
from modules.sleep_score import compute_sleep_score, verdict, WEIGHTS  # noqa: E402


def _baseline(hrv: float | None = 50.0, rhr: float | None = 58.0):
    return {
        "hrv_baseline": hrv,
        "rhr_baseline": rhr,
        "asleep_baseline_min": 480,
        "bed_time_stddev_min": 10.0,
        "sample_size": 28,
    }


def test_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-6


def test_perfect_night():
    night = SleepNight(date="2026-01-01", total_asleep_min=480,
                       deep_min=90, rem_min=120,
                       hrv_overnight_avg=60)
    r = compute_sleep_score(night, _baseline(), sleep_need_min=480)
    assert r["score"] >= 90
    assert r["verdict"] == "ready"


def test_zero_sleep():
    night = SleepNight(date="2026-01-01", total_asleep_min=0,
                       deep_min=0, rem_min=0, hrv_overnight_avg=None)
    r = compute_sleep_score(night, _baseline(), sleep_need_min=480)
    assert r["components"]["duration"]["score"] == 0
    assert r["score"] < 60
    assert r["verdict"] == "low"


def test_missing_hrv_doesnt_explode():
    night = SleepNight(date="2026-01-01", total_asleep_min=420,
                       deep_min=60, rem_min=100, hrv_overnight_avg=None)
    r = compute_sleep_score(night, _baseline(), sleep_need_min=480)
    # HRV gets the neutral 50, should not throw
    assert r["components"]["hrv"]["score"] == 50.0
    assert 0 <= r["score"] <= 100


def test_missing_baseline():
    night = SleepNight(date="2026-01-01", total_asleep_min=420,
                       deep_min=60, rem_min=100, hrv_overnight_avg=40)
    r = compute_sleep_score(night, _baseline(hrv=None), sleep_need_min=480)
    # HRV without baseline returns neutral 50
    assert r["components"]["hrv"]["score"] == 50.0


def test_verdict_thresholds():
    assert verdict(85) == "ready"
    assert verdict(79.9) == "moderate"
    assert verdict(60) == "moderate"
    assert verdict(59.9) == "low"


def test_short_sleep_penalty():
    night = SleepNight(date="2026-01-01", total_asleep_min=240,  # 4h
                       deep_min=40, rem_min=60, hrv_overnight_avg=50)
    r = compute_sleep_score(night, _baseline(), sleep_need_min=480)
    # 4h is 50% of need -> duration score = 50
    assert r["components"]["duration"]["score"] == 50


def test_components_present():
    night = SleepNight(date="2026-01-01", total_asleep_min=420,
                       deep_min=60, rem_min=90, hrv_overnight_avg=45)
    r = compute_sleep_score(night, _baseline(), sleep_need_min=480)
    assert set(r["components"].keys()) == {"duration", "depth_quality", "hrv", "consistency"}
    for c in r["components"].values():
        assert 0 <= c["score"] <= 100
