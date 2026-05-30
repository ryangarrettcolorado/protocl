"""v3.3 — per-user + per-app rate limits and cost estimation (spec 2.7)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st
import storage
from explainers import rate_limit
from storage import ProfileStorage


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(storage, "SHARED_DIR", tmp_path / "shared")
    monkeypatch.setattr(storage, "OWNER_LEGACY_DIR", tmp_path / "ryan")
    st.session_state.clear()
    st.session_state["profile_id"] = "alice"
    yield
    st.session_state.clear()


def _store():
    return ProfileStorage()


def test_spec_limits():
    assert rate_limit.TIER2_DAILY_LIMIT == 50
    assert rate_limit.TIER3_DAILY_LIMIT == 10
    assert rate_limit.APP_DAILY_LIMIT == 500


def test_fresh_user_has_full_quota():
    assert rate_limit.remaining(_store(), 2) == 50
    assert rate_limit.remaining(_store(), 3) == 10


def test_recording_decrements_quota():
    rate_limit.record_generation(_store(), 2)
    assert rate_limit.remaining(_store(), 2) == 49


def test_tier3_limit_enforced():
    for _ in range(10):
        rate_limit.record_generation(_store(), 3)
    assert rate_limit.remaining(_store(), 3) == 0
    assert rate_limit.can_generate(_store(), 3) is False


def test_app_budget_decrements_and_blocks_tier2_3():
    # Spend the entire app budget.
    for _ in range(rate_limit.APP_DAILY_LIMIT):
        rate_limit._increment_app()
    assert rate_limit.app_budget_remaining() == 0
    # Even with personal quota left, app ceiling blocks generation.
    assert rate_limit.can_generate(_store(), 2) is False


def test_tier1_pricing_cheaper_than_tier3_model():
    cost_mini = rate_limit.estimate_cost("gpt-4o-mini", 1000, 1000)
    cost_4o = rate_limit.estimate_cost("gpt-4o", 1000, 1000)
    assert cost_mini < cost_4o
    assert cost_mini > 0


def test_log_cost_writes_row():
    rate_limit.log_cost("alice", "apob_trend", 2, "gpt-4o-mini", 100, 50)
    df = rate_limit.read_cost_log()
    assert len(df) == 1
    assert df.iloc[0]["profile_id"] == "alice"
    assert df.iloc[0]["model"] == "gpt-4o-mini"
