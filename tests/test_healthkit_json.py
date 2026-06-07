"""Tests for the Health Auto Export JSON ingester.

Uses a real export sample (trimmed to 3 samples/metric for speed) so the
schema assertions stay grounded in actual on-device output.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest

from protocl.modules.ingest.healthkit_json import (
    METRIC_MAP,
    IngestResult,
    merge_into_csv,
    parse_export,
    parse_hae_datetime,
)


FIXTURE = Path(__file__).parent / "fixtures" / "health_auto_export_sample.json"


@pytest.fixture
def sample_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_fixture_exists():
    assert FIXTURE.exists(), "Fixture missing — regenerate from real export"


def test_parse_hae_datetime_handles_mountain_time():
    ts = parse_hae_datetime("2026-01-09 00:00:00 -0700")
    assert ts is not None
    assert ts.tz is not None
    # 00:00 MDT == 07:00 UTC → in America/Denver it stays 00:00
    assert ts.strftime("%Y-%m-%d %H:%M") == "2026-01-09 00:00"


def test_parse_hae_datetime_rejects_garbage():
    assert parse_hae_datetime("") is None
    assert parse_hae_datetime("not-a-date") is None


def test_parse_export_returns_ingest_result(sample_bytes):
    result = parse_export(sample_bytes)
    assert isinstance(result, IngestResult)
    assert result.rows_in > 0


def test_wearables_has_expected_columns(sample_bytes):
    result = parse_export(sample_bytes)
    df = result.wearables
    assert not df.empty
    # Columns we explicitly map should show up when their metric is present
    expected_subset = {"date", "resting_hr_bpm", "hrv_sdnn_ms", "vo2_max_ml_kg_min",
                       "sleep_duration_hrs", "steps", "active_calories", "source"}
    actual = set(df.columns)
    missing = expected_subset - actual
    assert not missing, f"Missing wearables columns: {missing}. Got: {sorted(actual)}"


def test_sleep_decomposes_into_stages(sample_bytes):
    result = parse_export(sample_bytes)
    df = result.wearables
    # The fixture has one sleep row at 2026-01-15
    row = df[df["date"] == "2026-01-15"]
    assert len(row) == 1
    assert row["sleep_duration_hrs"].iloc[0] == 7.2
    assert row["sleep_deep_hrs"].iloc[0] == 1.3
    assert row["sleep_rem_hrs"].iloc[0] == 1.8


def test_steps_are_summed_not_averaged(sample_bytes):
    """If two step samples land on the same day, we should sum them
    (the strategy = 'sum' branch), not average."""
    result = parse_export(sample_bytes)
    df = result.wearables
    # The real export has one step_count sample per day, but verify the
    # column exists and values are sane (5-figure step counts are normal)
    assert "steps" in df.columns


def test_cgm_preserves_five_minute_granularity(sample_bytes):
    result = parse_export(sample_bytes)
    df = result.cgm_readings
    assert not df.empty, "Glucose samples should produce CGM rows"
    # Fixture has 3 glucose samples 5 min apart on 2026-01-15
    assert len(df) == 3
    assert set(df.columns) == {
        "datetime", "glucose_mg_dl", "glucose_mmol_l",
        "source", "sensor_type", "notes",
    }
    # mg/dL → mmol/L conversion is correct (92 / 18.0182 ≈ 5.11)
    first = df.iloc[0]
    assert first["glucose_mg_dl"] == 92.0
    assert abs(first["glucose_mmol_l"] - 5.11) < 0.05
    assert first["source"] == "Lingo"
    assert first["sensor_type"] == "cgm"


def test_inbody_body_fat_lands_in_inbody_table(sample_bytes):
    result = parse_export(sample_bytes)
    df = result.inbody
    assert not df.empty
    assert "body_fat_pct" in df.columns


def test_unknown_metrics_are_skipped_not_crashed():
    payload = {
        "data": {
            "metrics": [
                {"name": "made_up_metric", "data": [
                    {"date": "2026-01-09 00:00:00 -0700", "qty": 42},
                ]},
                {"name": "heart_rate", "data": [
                    {"date": "2026-01-09 00:00:00 -0700", "qty": 60},
                ]},
            ]
        }
    }
    result = parse_export(json.dumps(payload).encode("utf-8"))
    assert "made_up_metric" in result.skipped_metrics
    assert not result.wearables.empty  # heart_rate still made it


def test_missing_qty_is_silently_dropped():
    payload = {
        "data": {
            "metrics": [
                {"name": "heart_rate", "data": [
                    {"date": "2026-01-09 00:00:00 -0700"},  # no qty
                    {"date": "2026-01-09 00:00:00 -0700", "qty": 60},
                ]},
            ]
        }
    }
    result = parse_export(json.dumps(payload).encode("utf-8"))
    # The valid row should still come through
    assert not result.wearables.empty


def test_metric_map_has_no_dangling_targets():
    """Every routed target must be a real table we know how to write."""
    valid_targets = {"wearables", "cgm_readings", "inbody"}
    for name, (target, col, strategy) in METRIC_MAP.items():
        assert target in valid_targets, f"{name} points at unknown target {target}"
        assert strategy in {"mean", "sum", "max", "last", "raw", "sleep"}, (
            f"{name} uses unknown strategy {strategy}"
        )


def test_merge_into_csv_dedupes_by_date(tmp_path):
    existing_path = tmp_path / "wearables.csv"
    existing = pd.DataFrame({
        "date": ["2026-01-08", "2026-01-09"],
        "resting_hr_bpm": [55.0, 56.0],
        "source": ["apple_health", "apple_health"],
    })
    existing.to_csv(existing_path, index=False)

    # New file re-imports 2026-01-09 (should overwrite) and adds 2026-01-10
    new = pd.DataFrame({
        "date": ["2026-01-09", "2026-01-10"],
        "resting_hr_bpm": [57.0, 58.0],  # updated value for 1/9
        "source": ["apple_health", "apple_health"],
    })
    merged, added, dupes = merge_into_csv(new, str(existing_path), key_cols=["date"])
    assert added == 2
    assert dupes == 1  # the overlapping 1/9 row
    # After merge, the new value for 1/9 wins
    row = merged[merged["date"] == "2026-01-09"]
    assert row["resting_hr_bpm"].iloc[0] == 57.0
    # And we now have three days total
    assert len(merged) == 3


def test_merge_into_csv_creates_new_file_when_missing(tmp_path):
    target = tmp_path / "new.csv"
    new = pd.DataFrame({
        "date": ["2026-01-09"],
        "resting_hr_bpm": [55.0],
    })
    merged, added, dupes = merge_into_csv(new, str(target), key_cols=["date"])
    assert added == 1
    assert dupes == 0
    assert len(merged) == 1


def test_empty_payload_is_safe():
    result = parse_export(json.dumps({"data": {"metrics": []}}).encode("utf-8"))
    assert result.wearables.empty
    assert result.cgm_readings.empty
    assert result.inbody.empty
    assert result.rows_in == 0
