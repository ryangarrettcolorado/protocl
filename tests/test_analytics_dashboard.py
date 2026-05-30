"""v3.6 — owner analytics aggregations (engagement, funnel, watchlist)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

import consent
from modules import analytics, events


NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)

ALLOWLIST = {
    "owner": {"email": "ryan@example.org"},
    "beta_users": [
        {"email": "alice@gmail.com"},
        {"email": "bob@gmail.com"},
        {"email": "placeholder@example.com"},  # ignored
    ],
}


def test_daily_active_from_rollup(isolate):
    s = make_store("alice")
    events.track("session_start", store=s, _now_dt=NOW)
    events.track("session_start", store=s, _now_dt=NOW)
    dau = analytics.daily_active()
    assert not dau.empty
    assert int(dau["count"].sum()) == 2


def test_top_pages_anonymized(isolate):
    s = make_store("alice")
    events.track("page_view", page="sleep", store=s)
    events.track("page_view", page="sleep", store=s)
    events.track("page_view", page="home", store=s)
    tp = analytics.top_pages()
    assert "profile_id" not in tp.columns
    top = tp.iloc[0]
    assert top["page"] == "sleep"
    assert int(top["count"]) == 2


def test_funnel_counts(isolate):
    # alice: consented + has events + 3 sessions → all stages
    a = make_store("alice_at_gmail_com")
    a.seed_empty()
    consent.record_consent(privacy_accepted=True, owner_visibility=False, store=a)
    for _ in range(3):
        events.track("session_start", store=a)
    # bob: seeded but no consent, no events
    b = make_store("bob_at_gmail_com")
    b.seed_empty()

    f = analytics.funnel_counts(ALLOWLIST)
    assert f["signed_up"] == 2          # alice + bob (owner ryan has no dir)
    assert f["consented"] == 1          # only alice
    assert f["first_data"] == 1         # only alice
    assert f["returned"] == 1           # only alice reached 3 sessions


def test_dropoff_watchlist_lists_inactive(isolate):
    a = make_store("alice_at_gmail_com")
    events.track("page_view", page="home", store=a, _now_dt=NOW - timedelta(days=10))
    b = make_store("bob_at_gmail_com")
    events.track("page_view", page="home", store=b, _now_dt=NOW - timedelta(days=2))

    wl = analytics.dropoff_watchlist(ALLOWLIST, now=NOW, min_days=7)
    ids = set(wl["profile_id"])
    assert "alice_at_gmail_com" in ids
    assert "bob_at_gmail_com" not in ids


def test_empty_rollup_safe(isolate):
    assert analytics.daily_active().empty
    assert analytics.weekly_active().empty
    assert analytics.top_pages().empty
