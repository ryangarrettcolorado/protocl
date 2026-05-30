"""v3.4 — adaptive UI state logic: dismiss window, hero transitions, toggle."""
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
from modules import locked_section as ls
from modules import setup_hero as sh


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


# ── locked_section dismissal window ──────────────────────────────────────────

def test_dismiss_then_is_dismissed():
    store = _store()
    assert ls.is_dismissed("bloodwork", store) is False
    ls.dismiss_nudge("bloodwork", store)
    assert ls.is_dismissed("bloodwork", store) is True


def test_dismiss_expires_after_30_days():
    store = _store()
    ls.dismiss_nudge("bloodwork", store)
    future = datetime.now(timezone.utc) + timedelta(days=31)
    assert ls.is_dismissed("bloodwork", store, now=future) is False


def test_dismiss_within_30_days_still_active():
    store = _store()
    ls.dismiss_nudge("bloodwork", store)
    soon = datetime.now(timezone.utc) + timedelta(days=29)
    assert ls.is_dismissed("bloodwork", store, now=soon) is True


def test_dismiss_is_per_source():
    store = _store()
    ls.dismiss_nudge("bloodwork", store)
    assert ls.is_dismissed("bloodwork", store) is True
    assert ls.is_dismissed("wearables", store) is False


# ── setup hero decision: pure transitions ────────────────────────────────────

def test_hero_renders_when_below_50_and_no_state():
    d = sh.hero_decision(15, None)
    assert d.action == "render" and d.should_render


def test_hero_skips_at_or_above_50():
    assert sh.hero_decision(50, None).action == "skip"
    assert sh.hero_decision(80, None).action == "skip"
    assert sh.hero_decision(50, None).should_render is False


def test_hero_full_lifecycle_render_dismiss_norender_milestone_render_expire():
    now = datetime.now(timezone.utc)
    # 1. render at 15%, no state
    assert sh.hero_decision(15, None, now=now).action == "render"
    # 2. dismiss → snooze state at 15%
    state = {"snoozed_at": now.isoformat(), "snoozed_at_pct": 15,
             "last_milestone_pct": 0}
    # 3. still 15%, within snooze → skip
    assert sh.hero_decision(15, state, now=now + timedelta(days=1)).action == "skip"
    # 4. crossed 25% milestone while snoozed → celebration render
    d = sh.hero_decision(30, state, now=now + timedelta(days=2))
    assert d.action == "render_celebration" and d.crossed_milestone == 25
    # 5. 14 days pass, still no new milestone → render (snooze expired)
    state2 = {"snoozed_at": now.isoformat(), "snoozed_at_pct": 30,
              "last_milestone_pct": 25}
    assert sh.hero_decision(30, state2, now=now + timedelta(days=14)).action == "render"


def test_hero_no_milestone_within_snooze_skips():
    now = datetime.now(timezone.utc)
    state = {"snoozed_at": now.isoformat(), "snoozed_at_pct": 10,
             "last_milestone_pct": 0}
    # bumped from 10% to 20% — no 25% milestone crossed yet → skip
    assert sh.hero_decision(20, state, now=now + timedelta(days=3)).action == "skip"


def test_hero_milestone_not_repeated_after_recorded():
    now = datetime.now(timezone.utc)
    # already recorded the 25% milestone; coverage still 30% → no re-celebration
    state = {"snoozed_at": now.isoformat(), "snoozed_at_pct": 10,
             "last_milestone_pct": 25}
    d = sh.hero_decision(30, state, now=now + timedelta(days=2))
    assert d.action == "skip"


def test_hero_50_milestone_caps_to_ceiling():
    # crossing 50 is moot — at 50% the ceiling rule fires first → skip.
    now = datetime.now(timezone.utc)
    state = {"snoozed_at": now.isoformat(), "snoozed_at_pct": 40,
             "last_milestone_pct": 25}
    assert sh.hero_decision(50, state, now=now + timedelta(days=1)).action == "skip"


# ── setup hero state IO ──────────────────────────────────────────────────────

def test_snooze_hero_persists_state():
    store = _store()
    sh.snooze_hero(15, store)
    state = sh.load_state(store)
    assert state["snoozed_at_pct"] == 15
    assert state["snoozed_at"]


def test_render_setup_hero_skips_when_coverage_high(monkeypatch):
    store = _store()
    monkeypatch.setattr(sh.dp, "data_coverage_pct", lambda s=None: 80)
    # Should return without touching st (no exception from the shim).
    assert sh.render_setup_hero(store) is None


# ── settings toggle overrides visibility ─────────────────────────────────────

def test_show_empty_toggle_forces_all_active(monkeypatch):
    store = _store()  # empty profile → everything hidden normally
    monkeypatch.setattr(dp, "show_empty_sections", lambda: True)
    for key in ("bloodwork", "wearables", "cgm", "ketones", "daily_log"):
        assert dp.visibility_state(key, store) == "active"


def test_show_empty_off_hides_empty(monkeypatch):
    store = _store()
    monkeypatch.setattr(dp, "show_empty_sections", lambda: False)
    assert dp.visibility_state("bloodwork", store) == "hidden"


def test_owner_default_show_empty_true(monkeypatch):
    # Owner with no explicit pref → show_empty defaults ON (rich-data UX).
    st.session_state["role"] = "owner"
    st.session_state["profile_id"] = "ryan"
    import modules.preferences as prefs_mod
    monkeypatch.setattr(prefs_mod, "load_preferences", lambda *a, **k: {"appearance": {}})
    assert dp.show_empty_sections() is True


def test_beta_default_show_empty_false(monkeypatch):
    st.session_state["role"] = "beta_user"
    st.session_state["profile_id"] = "friend_at_gmail_com"
    import modules.preferences as prefs_mod
    monkeypatch.setattr(prefs_mod, "load_preferences", lambda *a, **k: {"appearance": {}})
    assert dp.show_empty_sections() is False


def test_explicit_pref_overrides_role_default(monkeypatch):
    st.session_state["role"] = "beta_user"
    import modules.preferences as prefs_mod
    monkeypatch.setattr(prefs_mod, "load_preferences",
                        lambda *a, **k: {"appearance": {"show_empty_sections": True}})
    assert dp.show_empty_sections() is True
