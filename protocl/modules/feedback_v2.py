"""v3.6 — structured 3-question feedback widget (replaces free-text-only).

Three questions, sentiment first to lower friction:
  1. Sentiment (required): positive / mixed / negative
  2. "What did you expect to see here?" (free text, optional)
  3. "What's one thing that would make this better?" (free text, optional)

Auto-captured context: ``page_id``, ``profile_id`` (private), ``timestamp``,
``browser_user_agent``, and the last 5 events from the user's ``events.csv``.

Writes to the user's own ``feedback.csv`` AND appends the structured fields to
``data/shared/all_feedback.csv``. The original free-text path is preserved as a
"tell us more" message field beneath the three questions.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone

import streamlit as st

import storage
from modules import events
from storage import ProfileStorage


GLOBAL_FILE = "all_feedback.csv"
# Superset of the v3.2 schema so the owner admin can read old + new rows.
COLUMNS = ["timestamp", "profile_id", "display_name", "page", "message",
           "sentiment", "expected", "improvement", "user_agent", "recent_events"]

SENTIMENTS = ("positive", "mixed", "negative")
SENTIMENT_LABELS = {
    "positive": "👍 Useful",
    "mixed": "🤔 Mixed",
    "negative": "👎 Not useful",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit_structured(sentiment: str, expected: str = "", improvement: str = "",
                      message: str = "", page: str = "",
                      store: ProfileStorage | None = None,
                      display_name: str | None = None,
                      user_agent: str = "") -> None:
    """Persist a structured feedback row (per-user + shared). Sentiment required."""
    if sentiment not in SENTIMENTS:
        raise ValueError(f"sentiment must be one of {SENTIMENTS}, got {sentiment!r}")
    store = store or ProfileStorage()
    name = display_name or st.session_state.get("display_name") or store.profile_id
    recent = events.recent_events(5, store)
    row = {
        "timestamp": _now(),
        "profile_id": store.profile_id,
        "display_name": name,
        "page": page,
        "message": message.strip(),
        "sentiment": sentiment,
        "expected": expected.strip(),
        "improvement": improvement.strip(),
        "user_agent": user_agent,
        "recent_events": json.dumps(recent, default=str),
    }
    try:
        store.append_csv("feedback.csv", row)
    except Exception:
        pass
    storage.append_shared_csv(GLOBAL_FILE, row, COLUMNS)
    events.track("feedback_submitted", page=page, sentiment=sentiment, store=store)


def read_all_feedback():
    return storage.read_shared_csv(GLOBAL_FILE, parse_dates=["timestamp"])


def feedback_count(profile_id: str) -> int:
    df = read_all_feedback()
    if df.empty or "profile_id" not in df.columns:
        return 0
    return int((df["profile_id"] == profile_id).sum())


# ────────────────────────────────────────────────────────────────────────────
# TF-IDF top-complaints clustering (no sklearn, no LLM — plain Python)
# ────────────────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z][a-z']+")
_STOPWORDS = frozenset((
    "the", "and", "for", "but", "with", "this", "that", "have", "has", "had",
    "was", "were", "are", "you", "your", "would", "could", "should", "more",
    "less", "than", "then", "them", "they", "what", "when", "where", "which",
    "who", "how", "why", "its", "it's", "i'm", "i've", "can", "cant", "can't",
    "not", "all", "any", "out", "get", "got", "see", "use", "used", "using",
    "one", "thing", "things", "make", "made", "want", "like", "just", "really",
    "some", "very", "much", "from", "into", "about", "there", "here", "been",
    "being", "will", "wont", "won't", "did", "doesnt", "doesn't", "dont",
    "don't", "page", "app", "data",
))


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall((text or "").lower())
            if t not in _STOPWORDS and len(t) > 2]


def top_complaint_terms(texts, top_n: int = 12) -> list[tuple[str, float]]:
    """Rank terms across negative/mixed feedback by summed TF-IDF weight.

    ``texts`` is an iterable of free-text strings. Returns ``(term, score)``
    pairs, highest first. Pure Python — no sklearn, no model calls.
    """
    docs = [_tokenize(t) for t in texts if (t or "").strip()]
    docs = [d for d in docs if d]
    n_docs = len(docs)
    if n_docs == 0:
        return []

    df_counts: Counter[str] = Counter()
    for doc in docs:
        for term in set(doc):
            df_counts[term] += 1

    scores: Counter[str] = Counter()
    for doc in docs:
        tf = Counter(doc)
        length = len(doc)
        for term, count in tf.items():
            idf = math.log((1 + n_docs) / (1 + df_counts[term])) + 1.0
            scores[term] += (count / length) * idf

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_n]


# ────────────────────────────────────────────────────────────────────────────
# Sidebar widget
# ────────────────────────────────────────────────────────────────────────────

def render_sidebar_widget(current_page: str = "") -> None:
    """💬 Send feedback button → structured 3-question dialog."""
    with st.sidebar:
        if st.button("💬 Send feedback", use_container_width=True):
            st.session_state["_show_feedback"] = True

    if st.session_state.get("_show_feedback"):
        _render_dialog(current_page)


def _render_dialog(current_page: str) -> None:
    @st.dialog("Send feedback")  # type: ignore[misc]
    def _dialog() -> None:
        st.write("Three quick questions — only the first is required.")
        sentiment_key = st.radio(
            "How useful is this?",
            options=list(SENTIMENTS),
            format_func=lambda s: SENTIMENT_LABELS[s],
            horizontal=True,
            key="_fb_sentiment",
        )
        expected = st.text_input(
            "What did you expect to see here?",
            key="_fb_expected",
            placeholder="Optional — leave blank if everything's clear",
        )
        improvement = st.text_input(
            "What's one thing that would make this better?",
            key="_fb_improvement",
            placeholder="Optional",
        )
        message = ""
        with st.expander("Or tell us more →", expanded=False):
            message = st.text_area("Anything else?", key="_fb_message", height=100)
        if st.button("Submit", type="primary"):
            submit_structured(
                sentiment=sentiment_key,
                expected=expected,
                improvement=improvement,
                message=message,
                page=current_page,
            )
            st.session_state["_show_feedback"] = False
            st.success("Thanks — feedback sent!")
            st.rerun()

    _dialog()
