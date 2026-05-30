"""v3.6 — event tracking + anonymized rollup + session windowing."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import events, user_prefs


def test_track_writes_per_user_and_anon_rollup(isolate):
    store = make_store("alice")
    events.track("page_view", page="home", store=store)
    df = events.read_events(store)
    assert len(df) == 1
    assert df.iloc[0]["event_name"] == "page_view"
    # Rollup carries no profile_id.
    rollup = events.read_rollup()
    assert "profile_id" not in rollup.columns
    assert int(rollup["count"].sum()) == 1


def test_rollup_never_contains_profile_id(isolate):
    store = make_store("bob")
    for _ in range(3):
        events.track("session_start", store=store)
    rollup = events.read_rollup()
    assert list(rollup.columns) == events.ROLLUP_COLUMNS
    assert "profile_id" not in rollup.columns


def test_no_tracking_when_analytics_opted_out(isolate):
    store = make_store("carol")
    user_prefs.set_analytics_consent(False, store)
    events.track("page_view", page="home", store=store)
    assert events.read_events(store).empty
    assert events.read_rollup().empty


def test_page_view_rollup_keeps_page_granularity_anonymously(isolate):
    store = make_store("dave")
    events.track("page_view", page="sleep", store=store)
    events.track("page_view", page="sleep", store=store)
    events.track("page_view", page="home", store=store)
    rollup = events.read_rollup()
    keys = set(rollup["event_name"])
    assert "page_view:sleep" in keys
    assert "page_view:home" in keys
    assert "profile_id" not in rollup.columns


def test_distinct_session_starts_counts(isolate):
    store = make_store("erin")
    for _ in range(4):
        events.track("session_start", store=store)
    assert events.distinct_session_starts(store) == 4


def test_is_new_session_window():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert events.is_new_session(None, now) is True
    assert events.is_new_session(now - timedelta(minutes=10), now) is False
    assert events.is_new_session(now - timedelta(minutes=45), now) is True


def test_recent_events_returns_last_n(isolate):
    store = make_store("frank")
    for i in range(8):
        events.track("page_view", page=f"p{i}", store=store)
    recent = events.recent_events(5, store)
    assert len(recent) == 5
