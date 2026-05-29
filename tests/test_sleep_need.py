"""Tests for sleep_need adjustments."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

from modules.sleep_data import SleepNight  # noqa: E402
from modules.sleep_need import BASE_NEED_MIN, compute_sleep_need  # noqa: E402


def test_base_need_no_adjustments():
    r = compute_sleep_need(nights=[], wearables=pd.DataFrame(),
                            training=pd.DataFrame(), bloodwork=pd.DataFrame(),
                            today=pd.Timestamp("2026-05-29"))
    assert r["sleep_need_min"] == BASE_NEED_MIN
    assert r["adjustments"] == []


def test_training_strain_adds_minutes():
    training = pd.DataFrame([{"date": "2026-05-28", "moving_time_min": 120,
                               "avg_heart_rate": 155}])
    r = compute_sleep_need(nights=[], training=training,
                            today=pd.Timestamp("2026-05-29"))
    assert r["sleep_need_min"] > BASE_NEED_MIN
    labels = [a["label"] for a in r["adjustments"]]
    assert any("training" in l.lower() for l in labels)


def test_sleep_debt_carryover_kicks_in():
    nights = [
        SleepNight(date="2026-05-27", total_asleep_min=300),  # 5h
        SleepNight(date="2026-05-28", total_asleep_min=320),  # 5.3h
    ]
    r = compute_sleep_need(nights=nights, today=pd.Timestamp("2026-05-29"))
    labels = [a["label"] for a in r["adjustments"]]
    assert any("debt" in l.lower() or "carryover" in l.lower() for l in labels)


def test_hrv_trending_down():
    # 28 days of HRV: first 21 at 60ms, last 7 dropping to 50ms (>5% drop)
    dates = pd.date_range("2026-05-01", periods=28)
    hrv = [60.0] * 21 + [50.0] * 7
    wearables = pd.DataFrame({"date": dates, "hrv_sdnn_ms": hrv,
                               "resting_hr_bpm": [55] * 28})
    r = compute_sleep_need(nights=[], wearables=wearables,
                            today=pd.Timestamp("2026-05-29"))
    labels = [a["label"] for a in r["adjustments"]]
    assert any("hrv" in l.lower() for l in labels)
