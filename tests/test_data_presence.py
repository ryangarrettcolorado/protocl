"""v3.4 — data presence registry: states, coverage math, freshness."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st
import storage
from storage import ProfileStorage
from modules import data_presence as dp


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(storage, "OWNER_LEGACY_DIR", tmp_path / "ryan")
    st.session_state.clear()
    st.session_state["profile_id"] = "tester"
    st.session_state["role"] = "beta_user"
    yield
    st.session_state.clear()


def _store() -> ProfileStorage:
    return ProfileStorage()


def _write_bloodwork(store, n: int, *, day0: str = "2026-05-01") -> None:
    base = pd.Timestamp(day0)
    rows = [{
        "date": (base + pd.Timedelta(days=30 * i)).strftime("%Y-%m-%d"),
        "panel": "cardiovascular", "biomarker_canonical": "apob_mg_dl",
        "value": 70 + i, "unit": "mg/dL", "lab_ref_low": 0, "lab_ref_high": 90,
        "source_lab": "LabCorp", "notes": "",
    } for i in range(n)]
    store.write_csv("bloodwork.csv", pd.DataFrame(rows))


# ── empty profile ────────────────────────────────────────────────────────────

def test_empty_profile_all_hidden(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    for src in dp.all_sources():
        assert dp.visibility_state(src.key, store) == "hidden"
    assert dp.data_coverage_pct(store) == 0


def test_empty_profile_freshness_missing():
    store = _store()
    assert dp.freshness_state("bloodwork", store) == "missing"


# ── stub vs active ───────────────────────────────────────────────────────────

def test_one_bloodwork_row_is_stub(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    _write_bloodwork(store, 1)
    assert dp.has_data("bloodwork", store=store) is True
    assert dp.has_data("bloodwork", for_trend=True, store=store) is False
    assert dp.visibility_state("bloodwork", store) == "stub"
    assert dp.data_coverage_pct(store) > 0


def test_three_bloodwork_rows_is_active(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    _write_bloodwork(store, 3)
    assert dp.has_data("bloodwork", for_trend=True, store=store) is True
    assert dp.visibility_state("bloodwork", store) == "active"


# ── freshness ────────────────────────────────────────────────────────────────

def test_stale_but_present_is_active_and_stale(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    # 3 draws, all > 120 days old → bloodwork stale but visible.
    old = (datetime.now(timezone.utc) - timedelta(days=400)).strftime("%Y-%m-%d")
    _write_bloodwork(store, 3, day0=old)
    assert dp.freshness_state("bloodwork", store) == "stale"
    assert dp.visibility_state("bloodwork", store) == "active"


def test_recent_data_is_fresh(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    recent = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")
    _write_bloodwork(store, 3, day0=recent)
    # day0 + 60d is in the future relative to "now"; the max() draw is recent.
    assert dp.freshness_state("bloodwork", store) == "fresh"


def test_no_freshness_requirement_never_stale(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    store.write_csv("protocol.csv", pd.DataFrame([{
        "name": "Test", "category": "supplement", "dose": "1", "unit": "g",
        "frequency": "daily", "start_date": "2000-01-01", "end_date": "", "notes": "",
    }]))
    assert dp.freshness_state("protocol", store) == "fresh"


# ── coverage math ────────────────────────────────────────────────────────────

def test_coverage_partial_weighted(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    _write_bloodwork(store, 3)  # weight 3
    total = sum(s.weight for s in dp.all_sources() if s.weight > 0)
    assert dp.data_coverage_pct(store) == round(3 / total * 100)


def test_coverage_full_is_100(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    _write_bloodwork(store, 3)
    store.write_csv("inbody.csv", pd.DataFrame([{"date": "2026-05-01", "weight_lb": 180,
                    "body_fat_pct": 15, "skeletal_muscle_mass_lb": 80, "notes": ""}]))
    store.write_csv("wearables.csv", pd.DataFrame([{"date": "2026-05-01", "sleep_score": 80,
                    "hrv_ms": 60, "rhr_bpm": 50, "steps": 9000, "notes": ""}]))
    store.write_csv("training.csv", pd.DataFrame([{"date": "2026-05-01", "activity": "run",
                    "duration_min": 40, "avg_hr": 140, "notes": ""}]))
    store.write_csv("cgm_readings.csv", pd.DataFrame([{"datetime": "2026-05-01T08:00", "glucose_mg_dl": 95, "notes": ""}]))
    store.write_csv("ketone_readings.csv", pd.DataFrame([{"datetime": "2026-05-01T08:00", "ketones_mmol_l": 0.5, "notes": ""}]))
    store.write_csv("protocol.csv", pd.DataFrame([{"name": "X", "category": "supplement",
                    "dose": "1", "unit": "g", "frequency": "daily", "start_date": "2026-01-01", "end_date": "", "notes": ""}]))
    store.write_csv("daily_log.csv", pd.DataFrame([{"date": "2026-05-01", "weight_lb": 180,
                    "mood": "good", "energy": "high", "notes": ""}]))
    assert dp.data_coverage_pct(store) == 100


# ── show_empty override ──────────────────────────────────────────────────────

def test_show_empty_forces_active(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: True)
    store = _store()  # empty profile
    assert dp.visibility_state("bloodwork", store) == "active"
    assert dp.visibility_state("cgm", store) == "active"


# ── catalog integrity ────────────────────────────────────────────────────────

def test_registry_has_required_sources():
    keys = {s.key for s in dp.all_sources()}
    required = {"bloodwork", "inbody", "wearables", "training", "cgm",
                "ketones", "protocol", "daily_log", "strava",
                "function_health", "sleep"}
    assert required.issubset(keys)


def test_get_source_unknown_raises():
    with pytest.raises(KeyError):
        dp.get_source("nope")


def test_view_source_filter_counts_only_matching_rows(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    # Training rows without distance/tss → strava view sees nothing.
    store.write_csv("training.csv", pd.DataFrame([
        {"date": "2026-05-01", "activity_type": "strength", "duration_min": 60},
        {"date": "2026-05-02", "activity_type": "strength", "duration_min": 60},
        {"date": "2026-05-03", "activity_type": "strength", "duration_min": 60},
    ]))
    assert dp.has_data("training", for_trend=True, store=store) is True
    assert dp.has_data("strava", store=store) is False


def test_hidden_sources_ranked_by_weight(monkeypatch):
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    store = _store()
    ranked = dp.hidden_sources_ranked(store)
    assert ranked[0].key == "bloodwork"  # weight 3 leads
    weights = [s.weight for s in ranked]
    assert weights == sorted(weights, reverse=True)
