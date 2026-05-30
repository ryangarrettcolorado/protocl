"""v3.5 — sync orchestrator: opt-in gating, cap, per-source isolation."""
from __future__ import annotations

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import sync_orchestrator as so
from modules import user_prefs


ALLOWLIST = {
    "owner": {"email": "ryan@example.org"},
    "beta_users": [
        {"email": "alice@gmail.com"},
        {"email": "placeholder@example.com"},  # skipped
    ],
}


def _opt_in(profile_id, *sources):
    store = make_store(profile_id)
    for s in sources:
        user_prefs.set_auto_sync(s, True, store)


def test_skips_users_without_optin(isolate):
    # Nobody opted in → zero runs.
    report = so.run_daily_sync_for_all_profiles(ALLOWLIST, runner=lambda p, s: 5)
    assert report.runs_used == 0
    assert report.results == []


def test_runs_only_optin_sources(isolate):
    _opt_in("ryan", "strava")
    _opt_in("alice_at_gmail_com", "apple_health")
    calls = []
    report = so.run_daily_sync_for_all_profiles(
        ALLOWLIST, runner=lambda p, s: calls.append((p, s)) or 3
    )
    assert ("ryan", "strava") in calls
    assert ("alice_at_gmail_com", "apple_health") in calls
    assert report.runs_used == 2
    assert report.ok_count == 2


def test_per_source_error_isolation(isolate):
    _opt_in("alice_at_gmail_com", "strava", "apple_health")

    def runner(p, s):
        if s == "strava":
            raise RuntimeError("token expired")
        return 7

    report = so.run_daily_sync_for_all_profiles(ALLOWLIST, runner=runner)
    assert report.error_count == 1
    assert report.ok_count == 1
    # The good source still recorded its records.
    ok = [r for r in report.results if r.status == "ok"][0]
    assert ok.records_added == 7


def test_daily_cap_enforced(isolate):
    _opt_in("ryan", "strava", "apple_health")
    _opt_in("alice_at_gmail_com", "strava", "apple_health")
    report = so.run_daily_sync_for_all_profiles(ALLOWLIST, runner=lambda p, s: 1, cap=2)
    assert report.runs_used == 2
    assert report.budget_reached is True
    skipped = [r for r in report.results if r.status == "skipped"]
    assert len(skipped) >= 1


def test_sync_log_written(isolate):
    _opt_in("alice_at_gmail_com", "strava")
    so.run_daily_sync_for_all_profiles(ALLOWLIST, runner=lambda p, s: 4)
    log = so.read_sync_log()
    assert not log.empty
    assert "alice_at_gmail_com" in set(log["profile_id"].astype(str))
