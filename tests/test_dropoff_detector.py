"""v3.6 — drop-off staging, idempotency, and reset-on-activity."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import dropoff, events, user_prefs


NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def _seed_last_event(store, days_ago):
    ts = NOW - timedelta(days=days_ago)
    events.track("page_view", page="home", store=store, _now_dt=ts)


def test_stage_for_thresholds():
    assert dropoff.stage_for(3) == 0
    assert dropoff.stage_for(7) == 1
    assert dropoff.stage_for(14) == 2
    assert dropoff.stage_for(30) == 3
    assert dropoff.stage_for(99) == 3


def test_owner_never_actioned(isolate):
    store = make_store("ryan")
    _seed_last_event(store, 99)
    action = dropoff.evaluate_profile("ryan", now=NOW)
    assert action.action == "none"


def test_7day_nudge_sets_pref(isolate):
    store = make_store("alice")
    _seed_last_event(store, 8)
    action = dropoff.evaluate_profile("alice", now=NOW)
    assert action.action == "nudge"
    assert user_prefs.get("dropoff_nudge", None, store) == dropoff.NUDGE_MESSAGE
    assert int(user_prefs.get("dropoff_stage_actioned", 0, store)) == 1


def test_30day_pauses_autosync(isolate):
    store = make_store("bob")
    user_prefs.set_auto_sync("strava", True, store)
    _seed_last_event(store, 31)
    action = dropoff.evaluate_profile("bob", now=NOW)
    assert action.action == "auto_pause"
    assert user_prefs.auto_sync_enabled("strava", store) is False


def test_stage_fires_once_per_spell(isolate):
    store = make_store("carol")
    _seed_last_event(store, 8)
    first = dropoff.evaluate_profile("carol", now=NOW)
    assert first.action == "nudge"
    # Same inactivity → no repeat nudge.
    second = dropoff.evaluate_profile("carol", now=NOW)
    assert second.action == "none"


def test_activity_resets_spell(isolate):
    store = make_store("dave")
    _seed_last_event(store, 8)
    dropoff.evaluate_profile("dave", now=NOW)
    assert int(user_prefs.get("dropoff_stage_actioned", 0, store)) == 1
    # User comes back: a fresh event today.
    _seed_last_event(store, 0)
    action = dropoff.evaluate_profile("dave", now=NOW)
    assert action.action == "none"
    assert int(user_prefs.get("dropoff_stage_actioned", 0, store)) == 0
    assert user_prefs.get("dropoff_nudge", None, store) is None


def test_no_events_is_noop(isolate):
    make_store("erin")
    action = dropoff.evaluate_profile("erin", now=NOW)
    assert action.action == "none"
