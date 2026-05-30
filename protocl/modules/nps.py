"""v3.6 — one-tap NPS micro-survey.

Auto-triggers a single 0–10 question at the user's 7th distinct
``session_start`` (so they've had real exposure first), then re-surveys at the
30th and 60th session. A submit *or* dismiss suppresses the modal until the
next milestone. Responses (with the user's session count at the time) go to the
shared ``data/shared/nps_responses.csv``.

Scoring follows the standard buckets:
  detractor 0–6 · passive 7–8 · promoter 9–10.

No LLM, no external calls. All persistence flows through ``ProfileStorage`` /
``storage.append_shared_csv`` so v3.2 isolation holds.
"""
from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

import storage
from modules import events
from modules import user_prefs
from storage import ProfileStorage


RESPONSES_FILE = "nps_responses.csv"
COLUMNS = ["timestamp", "profile_id", "score", "reason", "days_active_at_response"]

# Session-count milestones at which we (re-)ask.
MILESTONES = (7, 30, 60)

# user_prefs keys tracking suppression state.
_PREF_LAST_PROMPT = "nps_last_prompt_milestone"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def categorize(score: int) -> str:
    """Standard NPS bucket for a 0–10 score."""
    if score <= 6:
        return "detractor"
    if score <= 8:
        return "passive"
    return "promoter"


def _last_prompted_milestone(store: ProfileStorage) -> int:
    val = user_prefs.get(_PREF_LAST_PROMPT, 0, store)
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0


def due_milestone(sessions: int, last_prompted: int) -> int | None:
    """Return the milestone we should prompt for, or None.

    We prompt for the *highest* milestone the user has reached that hasn't yet
    been prompted. ``last_prompted`` is the most recent milestone already shown
    (submitted or dismissed).
    """
    reached = [m for m in MILESTONES if sessions >= m and m > last_prompted]
    return max(reached) if reached else None


def should_prompt(store: ProfileStorage | None = None) -> int | None:
    """Milestone to prompt at right now, or None.

    Suppressed entirely when the user has opted out of analytics — we don't
    collect anything (not even prompt state) for those users.
    """
    store = store or ProfileStorage()
    if getattr(store, "read_only", False):
        return None
    if not user_prefs.analytics_allowed(store):
        return None
    sessions = events.distinct_session_starts(store)
    return due_milestone(sessions, _last_prompted_milestone(store))


def _mark_prompted(milestone: int, store: ProfileStorage) -> None:
    user_prefs.set_value(_PREF_LAST_PROMPT, int(milestone), store)


def submit(score: int, reason: str = "", *, milestone: int | None = None,
           store: ProfileStorage | None = None) -> None:
    """Persist an NPS response and suppress further prompts until the next
    milestone."""
    if not 0 <= int(score) <= 10:
        raise ValueError(f"score must be 0–10, got {score!r}")
    store = store or ProfileStorage()
    sessions = events.distinct_session_starts(store)
    row = {
        "timestamp": _now(),
        "profile_id": store.profile_id,
        "score": int(score),
        "reason": (reason or "").strip(),
        "days_active_at_response": sessions,
    }
    storage.append_shared_csv(RESPONSES_FILE, row, COLUMNS)
    _mark_prompted(milestone or sessions, store)
    events.track("nps_submitted", store=store, score=int(score))


def dismiss(milestone: int, store: ProfileStorage | None = None) -> None:
    """Suppress the modal at this milestone without recording a score."""
    store = store or ProfileStorage()
    _mark_prompted(milestone, store)
    events.track("nps_dismissed", store=store)


def read_responses():
    return storage.read_shared_csv(RESPONSES_FILE, parse_dates=["timestamp"])


def summary() -> dict[str, object]:
    """Aggregate NPS = %promoters − %detractors (latest response per user)."""
    df = read_responses()
    if df.empty or "score" not in df.columns:
        return {"n": 0, "nps": None, "promoters": 0, "passives": 0, "detractors": 0}
    latest = (
        df.sort_values("timestamp").groupby("profile_id", as_index=False).last()
        if "profile_id" in df.columns else df
    )
    scores = latest["score"].dropna().astype(int)
    n = len(scores)
    if n == 0:
        return {"n": 0, "nps": None, "promoters": 0, "passives": 0, "detractors": 0}
    promoters = int((scores >= 9).sum())
    detractors = int((scores <= 6).sum())
    passives = n - promoters - detractors
    nps = round((promoters - detractors) / n * 100, 1)
    return {"n": n, "nps": nps, "promoters": promoters,
            "passives": passives, "detractors": detractors}


# ────────────────────────────────────────────────────────────────────────────
# Modal (called from the shell on each render)
# ────────────────────────────────────────────────────────────────────────────

def maybe_render_modal(store: ProfileStorage | None = None) -> None:
    """Show the one-tap NPS modal if the user is due. Import-safe under tests."""
    store = store or ProfileStorage()
    milestone = should_prompt(store)
    if milestone is None:
        return

    @st.dialog("Quick question")  # type: ignore[misc]
    def _dialog() -> None:
        st.write("How likely are you to recommend Protocōl to a friend?")
        score = st.slider("0 = not at all · 10 = extremely", 0, 10, 8, key="_nps_score")
        reason = st.text_input(
            "What's the main reason for your score? (optional)", key="_nps_reason"
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Submit", type="primary", use_container_width=True):
                submit(score, reason, milestone=milestone, store=store)
                st.success("Thanks — that helps a lot.")
                st.rerun()
        with c2:
            if st.button("Not now", use_container_width=True):
                dismiss(milestone, store)
                st.rerun()

    _dialog()
