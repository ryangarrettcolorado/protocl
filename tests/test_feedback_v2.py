"""v3.6 — structured feedback + TF-IDF complaint clustering."""
from __future__ import annotations

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import feedback_v2


def test_submit_structured_requires_valid_sentiment(isolate):
    store = make_store("alice")
    with pytest.raises(ValueError):
        feedback_v2.submit_structured(sentiment="meh", store=store)


def test_submit_writes_shared_and_per_user(isolate):
    store = make_store("alice")
    feedback_v2.submit_structured(
        sentiment="negative", expected="more charts", improvement="fix sleep score",
        page="sleep", store=store, display_name="Alice",
    )
    shared = feedback_v2.read_all_feedback()
    assert len(shared) == 1
    row = shared.iloc[0]
    assert row["sentiment"] == "negative"
    assert row["page"] == "sleep"
    assert row["profile_id"] == "alice"
    # recent_events attached as JSON.
    assert "recent_events" in shared.columns


def test_feedback_count_per_profile(isolate):
    a = make_store("alice")
    feedback_v2.submit_structured(sentiment="positive", store=a)
    feedback_v2.submit_structured(sentiment="mixed", store=a)
    b = make_store("bob")
    feedback_v2.submit_structured(sentiment="negative", store=b)
    assert feedback_v2.feedback_count("alice") == 2
    assert feedback_v2.feedback_count("bob") == 1


def test_tfidf_ranks_recurring_terms_higher():
    texts = [
        "the sleep score is wrong and confusing",
        "sleep score wrong again today",
        "sleep score keeps showing wrong numbers",
        "export pdf is broken",
    ]
    terms = dict(feedback_v2.top_complaint_terms(texts, top_n=10))
    assert "sleep" in terms and "score" in terms
    # A term in 3 docs should outrank one in a single doc.
    assert terms["sleep"] > terms["export"]


def test_tfidf_empty_input():
    assert feedback_v2.top_complaint_terms([]) == []
    assert feedback_v2.top_complaint_terms(["", "   "]) == []


def test_tfidf_drops_stopwords():
    terms = dict(feedback_v2.top_complaint_terms(["the and for with this that"]))
    assert terms == {}
