"""v3.3 — explainer cache: data_hash stability, tiers, TTL, invalidation."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st
import storage
from explainers import cache
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


def test_data_hash_is_order_independent():
    assert cache.data_hash({"a": 1, "b": 2}) == cache.data_hash({"b": 2, "a": 1})


def test_data_hash_changes_with_content():
    assert cache.data_hash({"a": 1}) != cache.data_hash({"a": 2})


def test_tier1_cache_round_trip():
    h = cache.data_hash({"x": 1})
    assert cache.get_tier1("apob_trend", h) is None
    cache.set_tier1("apob_trend", h, "hello")
    assert cache.get_tier1("apob_trend", h) == "hello"


def test_tier1_ttl_expiry(monkeypatch):
    h = cache.data_hash({"x": 1})
    cache.set_tier1("apob_trend", h, "stale")
    # Jump clock past the 30-day TTL.
    real = time.time()
    monkeypatch.setattr(cache.time, "time", lambda: real + cache.TIER1_TTL_SECONDS + 10)
    assert cache.get_tier1("apob_trend", h) is None


def test_tier2_user_cache_is_per_profile():
    h = cache.data_hash({"v": 9})
    store_a = ProfileStorage()
    cache.set_user(store_a, "sleep_score_trend", h, 2, "alice-text")
    assert cache.get_user(store_a, "sleep_score_trend", h, 2) == "alice-text"
    # Bob's cache is separate.
    st.session_state["profile_id"] = "bob"
    store_b = ProfileStorage()
    assert cache.get_user(store_b, "sleep_score_trend", h, 2) is None


def test_tier2_invalidates_when_data_hash_changes():
    store = ProfileStorage()
    h1 = cache.data_hash({"v": 1})
    cache.set_user(store, "c", h1, 2, "first")
    h2 = cache.data_hash({"v": 2})
    assert cache.get_user(store, "c", h2, 2) is None  # new data → miss


def test_cached_explainer_tier1_calls_fn_once():
    calls = {"n": 0}

    @cache.cached_explainer(1)
    def gen(chart_id, data, **kw):
        calls["n"] += 1
        return f"gen-{calls['n']}"

    out1 = gen("apob_trend", {"d": 1})
    out2 = gen("apob_trend", {"d": 1})
    assert out1 == out2
    assert calls["n"] == 1  # second call served from cache


def test_cached_explainer_tier3_never_cached():
    calls = {"n": 0}

    @cache.cached_explainer(3)
    def gen(chart_id, data, **kw):
        calls["n"] += 1
        return "x"

    gen("c", {"d": 1})
    gen("c", {"d": 1})
    assert calls["n"] == 2
