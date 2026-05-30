"""v3.3 — deterministic Tier-1 rule engine (spec 2.4)."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

from explainers import rules
from explainers import registry


def _series(values, dates):
    return pd.DataFrame({"date": pd.to_datetime(dates), "value": values})


def test_all_14_tier1_biomarkers_defined():
    assert len(rules.TIER1_BIOMARKERS) == 14


def test_registry_tier1_keys_exist_in_rules():
    for s in registry.SURFACES:
        if s.tier1_biomarker:
            assert s.tier1_biomarker in rules.TIER1_BIOMARKERS


def test_no_data_returns_no_data_status():
    out = rules.evaluate("apob", None)
    assert out["status"] == "no_data"
    assert out["user_value"] is None
    assert out["biomarker"] == "apob_mg_dl"


def test_within_optimal_apob():
    # apob optimal 40–70, lab 40–125
    out = rules.evaluate("apob", _series([55], ["2026-01-01"]))
    assert out["status"] == "within_optimal"
    assert out["user_value"] == 55
    assert out["optimal_range"] == [40, 70]


def test_above_optimal_but_within_lab():
    out = rules.evaluate("apob", _series([90], ["2026-01-01"]))
    assert out["status"] == "above_optimal"
    assert "dietary_review" in out["recommendation_tags"]


def test_flag_high_outside_lab():
    out = rules.evaluate("apob", _series([200], ["2026-01-01"]))
    assert out["status"] == "flag_high"
    assert out["recommendation_tags"]  # high tags surfaced


def test_rising_trend_and_velocity():
    out = rules.evaluate("apob", _series([40, 70], ["2026-01-01", "2026-04-01"]))
    assert out["trend_direction"] == "rising"
    assert out["trend_velocity_per_quarter"] > 0


def test_falling_trend():
    out = rules.evaluate("apob", _series([90, 50], ["2026-01-01", "2026-07-01"]))
    assert out["trend_direction"] == "falling"
    assert out["trend_velocity_per_quarter"] < 0


def test_engine_is_deterministic():
    s = _series([45, 60, 72], ["2026-01-01", "2026-04-01", "2026-07-01"])
    r1 = rules.evaluate("apob", s.copy())
    r2 = rules.evaluate("apob", s.copy())
    assert r1 == r2


def test_unknown_biomarker_raises():
    with pytest.raises(KeyError):
        rules.evaluate("not_a_marker", _series([1], ["2026-01-01"]))


def test_output_schema_keys_present():
    out = rules.evaluate("hscrp", _series([0.5], ["2026-01-01"]))
    for key in ("biomarker", "label", "unit", "optimal_range", "lab_range",
                "status", "user_value", "trend_direction",
                "trend_velocity_per_quarter", "quarters_to_threshold",
                "recommendation_tags"):
        assert key in out
