"""v3.6 — NPS trigger cadence, scoring, persistence."""
from __future__ import annotations

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import events, nps, user_prefs


def _seed_sessions(store, n):
    for _ in range(n):
        events.track("session_start", store=store)


def test_categorize_buckets():
    assert nps.categorize(0) == "detractor"
    assert nps.categorize(6) == "detractor"
    assert nps.categorize(7) == "passive"
    assert nps.categorize(8) == "passive"
    assert nps.categorize(9) == "promoter"
    assert nps.categorize(10) == "promoter"


def test_due_milestone_progression():
    assert nps.due_milestone(6, 0) is None
    assert nps.due_milestone(7, 0) == 7
    assert nps.due_milestone(7, 7) is None
    assert nps.due_milestone(30, 7) == 30
    assert nps.due_milestone(65, 30) == 60
    assert nps.due_milestone(100, 60) is None


def test_should_prompt_at_7th_session(isolate):
    store = make_store("alice")
    _seed_sessions(store, 6)
    assert nps.should_prompt(store) is None
    _seed_sessions(store, 1)
    assert nps.should_prompt(store) == 7


def test_should_prompt_suppressed_without_analytics(isolate):
    store = make_store("bob")
    user_prefs.set_analytics_consent(False, store)
    # session_start won't even record, but force the check explicitly.
    assert nps.should_prompt(store) is None


def test_submit_persists_and_suppresses(isolate):
    store = make_store("carol")
    _seed_sessions(store, 7)
    assert nps.should_prompt(store) == 7
    nps.submit(9, "love the trends", milestone=7, store=store)
    df = nps.read_responses()
    assert len(df) == 1
    assert int(df.iloc[0]["score"]) == 9
    assert df.iloc[0]["profile_id"] == "carol"
    # Suppressed until the next milestone.
    assert nps.should_prompt(store) is None


def test_dismiss_suppresses_without_recording(isolate):
    store = make_store("dave")
    _seed_sessions(store, 7)
    nps.dismiss(7, store)
    assert nps.read_responses().empty
    assert nps.should_prompt(store) is None


def test_submit_rejects_out_of_range(isolate):
    store = make_store("erin")
    with pytest.raises(ValueError):
        nps.submit(11, store=store)


def test_summary_computes_nps(isolate):
    # 2 promoters, 1 detractor, 1 passive → NPS = (2-1)/4*100 = 25
    for pid, score in [("a", 9), ("b", 10), ("c", 3), ("d", 8)]:
        s = make_store(pid)
        _seed_sessions(s, 7)
        nps.submit(score, milestone=7, store=s)
    out = nps.summary()
    assert out["n"] == 4
    assert out["promoters"] == 2
    assert out["detractors"] == 1
    assert out["passives"] == 1
    assert out["nps"] == 25.0
