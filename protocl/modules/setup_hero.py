"""v3.4 Adaptive UI — Layer 2: the Home "setup progress" hero.

While a profile is below 50% data coverage, Home shows a polite progress hero
with the top quick wins. It can be snoozed for 14 days, but it *resurfaces*
when the user crosses a 25% or 50% milestone so progress feels rewarding. Once
coverage reaches 50% it never renders again.

The owner (rich data, ≥50% coverage) never sees the hero — the render decision
is pure and lives in :func:`hero_decision` so the transitions are unit-tested
without Streamlit.

State persists per-profile in ``setup_hero_state.json``:
    {"snoozed_at": "...", "snoozed_at_pct": 15, "last_milestone_pct": 0}
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import streamlit as st

from storage import ProfileStorage, ReadOnlyError
from modules import data_presence as dp

STATE_FILE = "setup_hero_state.json"
SNOOZE_DAYS = 14
MILESTONES = (25, 50)
COVERAGE_CEILING = 50  # at or above this, the hero never renders


HeroAction = Literal["render", "render_celebration", "skip"]


@dataclass(frozen=True)
class HeroDecision:
    action: HeroAction
    coverage_pct: int
    crossed_milestone: int | None = None

    @property
    def should_render(self) -> bool:
        return self.action in ("render", "render_celebration")


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _highest_milestone_crossed(prev_pct: int, now_pct: int) -> int | None:
    """The highest milestone strictly above ``prev_pct`` and at/below ``now_pct``."""
    crossed = [m for m in MILESTONES if prev_pct < m <= now_pct]
    return max(crossed) if crossed else None


def hero_decision(coverage_pct: int, state: dict | None,
                  *, now: datetime | None = None) -> HeroDecision:
    """Pure render decision for the setup hero.

    Rules (from the spec):
      - coverage ≥ 50%                       → never render
      - coverage < 50% and not snoozed       → render
      - snoozed, no milestone since snooze   → skip
      - snoozed but milestone crossed        → render with celebration
      - snooze expired (14 days)             → render
    """
    if coverage_pct >= COVERAGE_CEILING:
        return HeroDecision("skip", coverage_pct)

    state = state or {}
    snoozed_at = _parse_ts(state.get("snoozed_at"))
    if snoozed_at is None:
        return HeroDecision("render", coverage_pct)

    now = now or datetime.now(timezone.utc)
    snooze_expired = now - snoozed_at >= timedelta(days=SNOOZE_DAYS)

    snoozed_pct = int(state.get("snoozed_at_pct", 0) or 0)
    last_milestone = int(state.get("last_milestone_pct", 0) or 0)
    baseline = max(snoozed_pct, last_milestone)
    crossed = _highest_milestone_crossed(baseline, coverage_pct)

    if crossed is not None:
        return HeroDecision("render_celebration", coverage_pct, crossed)
    if snooze_expired:
        return HeroDecision("render", coverage_pct)
    return HeroDecision("skip", coverage_pct)


# ────────────────────────────────────────────────────────────────────────────
# State IO
# ────────────────────────────────────────────────────────────────────────────

def _store_or_default(store: ProfileStorage | None) -> ProfileStorage:
    return store if store is not None else ProfileStorage()


def load_state(store: ProfileStorage | None = None) -> dict:
    store = _store_or_default(store)
    state = store.read_json(STATE_FILE, default={}) or {}
    return state if isinstance(state, dict) else {}


def snooze_hero(coverage_pct: int, store: ProfileStorage | None = None) -> None:
    """Record a 14-day snooze at the current coverage."""
    store = _store_or_default(store)
    state = load_state(store)
    state["snoozed_at"] = datetime.now(timezone.utc).isoformat()
    state["snoozed_at_pct"] = int(coverage_pct)
    state.setdefault("last_milestone_pct", 0)
    _save(store, state)


def record_milestone(milestone_pct: int, store: ProfileStorage | None = None) -> None:
    """Mark that a celebration milestone has been shown so it isn't repeated."""
    store = _store_or_default(store)
    state = load_state(store)
    state["last_milestone_pct"] = max(int(state.get("last_milestone_pct", 0) or 0),
                                      int(milestone_pct))
    _save(store, state)


def _save(store: ProfileStorage, state: dict) -> None:
    try:
        store.write_json(STATE_FILE, state)
    except ReadOnlyError:
        pass  # impersonation is read-only; skip silently


# ────────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────────

def render_setup_hero(store: ProfileStorage | None = None) -> None:
    """Render the Home setup hero when the decision says so."""
    store = _store_or_default(store)
    coverage = dp.data_coverage_pct(store)
    decision = hero_decision(coverage, load_state(store))
    if not decision.should_render:
        return

    if decision.action == "render_celebration" and decision.crossed_milestone:
        record_milestone(decision.crossed_milestone, store)
        st.markdown(
            f"<div style='background:rgba(63,191,127,0.12);border:1px solid "
            f"rgba(63,191,127,0.4);border-radius:8px;padding:0.5rem 0.9rem;"
            f"margin-bottom:0.6rem;color:#3FBF7F;font-weight:600;'>"
            f"🎉 Nice — you just crossed {decision.crossed_milestone}% setup!</div>",
            unsafe_allow_html=True,
        )

    filled = int(round(coverage / 100 * 40))
    bar = "▓" * filled + "░" * (40 - filled)
    st.markdown(
        f"<div style='background:#1C1C1C;border:1px solid rgba(255,182,18,0.25);"
        f"border-radius:10px;padding:1rem 1.2rem;margin-bottom:1rem;'>"
        f"<div style='font-size:1.15rem;font-weight:700;color:#F0F0F0;'>"
        f"Welcome back — you're at {coverage}% setup</div>"
        f"<div style='font-family:monospace;color:#FFB612;margin:0.4rem 0;"
        f"letter-spacing:1px;'>{bar} &nbsp;{coverage} / 100</div></div>",
        unsafe_allow_html=True,
    )

    quick_wins = dp.hidden_sources_ranked(store)[:3]
    if quick_wins:
        from modules.add_data_modal import open_add_data_modal

        n = len(quick_wins)
        st.markdown(f"**{n} quick win{'s' if n != 1 else ''} to unlock more charts:**")
        for src in quick_wins:
            cols = st.columns([5, 2])
            with cols[0]:
                st.markdown(f"{src.icon} {src.value_prop or src.label}")
            with cols[1]:
                if st.button(f"Add {src.label.split('(')[0].strip()}",
                             key=f"hero_add_{src.key}", use_container_width=True):
                    open_add_data_modal(src.key)

    foot = st.columns([2, 2])
    with foot[0]:
        if st.button("Dismiss for 2 weeks", key="hero_snooze"):
            snooze_hero(coverage, store)
            st.rerun()
    with foot[1]:
        st.caption("Toggle **Show all sections** in Settings to see everything →")
