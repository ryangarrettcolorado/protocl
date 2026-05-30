"""v3.6 — drop-off detection logic.

Pure, testable logic for the daily drop-off cron (``scripts/dropoff_detector.py``).
Stages, by days since a user's last recorded activity:

  - **7 days**  → in-app re-engagement nudge (stored on the user's prefs so the
    Home banner can show it). Logged ``dropoff_nudge_sent``.
  - **14 days** → notify the owner (in-app inbox + best-effort email).
    Logged ``dropoff_owner_notified``.
  - **30 days** → auto-pause the user's auto-sync sources to stop spending
    credits on an absent user. Logged ``dropoff_sync_paused``.

Each stage fires at most once per inactivity spell: ``dropoff_stage_actioned``
on the user's prefs records the highest stage already handled, and resets to 0
the moment the user is active again (days_inactive below the first threshold).

No LLM. All reads/writes flow through ``ProfileStorage`` so v3.2 isolation
holds; the owner is never auto-paused or nudged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import audit
import owner_inbox
from auth import OWNER_PROFILE_ID
from modules import events, sync_orchestrator, user_prefs
from storage import ProfileStorage


NUDGE_DAYS = 7
OWNER_NOTIFY_DAYS = 14
AUTO_PAUSE_DAYS = 30

_STAGE_NUDGE = 1
_STAGE_OWNER = 2
_STAGE_PAUSE = 3

NUDGE_MESSAGE = (
    "We haven't seen you in a while — your health data may be out of date. "
    "Reconnect a source or check your latest trends."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def stage_for(days_inactive: float) -> int:
    """Highest drop-off stage warranted by this inactivity, or 0."""
    if days_inactive >= AUTO_PAUSE_DAYS:
        return _STAGE_PAUSE
    if days_inactive >= OWNER_NOTIFY_DAYS:
        return _STAGE_OWNER
    if days_inactive >= NUDGE_DAYS:
        return _STAGE_NUDGE
    return 0


def days_inactive(profile_id: str, now: datetime | None = None) -> float | None:
    """Days since this profile's last login, or None if it has never logged in.

    Per spec 2.4 the signal is the last ``login`` row in the shared audit log,
    so users who opted OUT of analytics (and therefore have no events) are still
    detected. Falls back to the last recorded event when no login row exists.
    """
    now = now or _now()
    last = audit.last_login(profile_id)
    if last is None:
        last = events.last_event_time(_store_for(profile_id))
    if last is None:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (now - last).total_seconds() / 86400.0


def _store_for(profile_id: str) -> ProfileStorage:
    s = ProfileStorage()
    s.profile_id = profile_id
    s.read_only = False
    return s


@dataclass
class DropoffAction:
    profile_id: str
    days_inactive: float
    stage: int
    action: str  # "nudge" | "owner_notify" | "auto_pause" | "none"


def _apply_stage(profile_id: str, days: float, stage: int,
                 store: ProfileStorage, owner_email: str | None) -> str:
    if stage == _STAGE_NUDGE:
        user_prefs.set_value("dropoff_nudge", NUDGE_MESSAGE, store)
        audit.log("dropoff_nudge_sent", profile_id=profile_id,
                  details=f"{days:.0f}d inactive")
        return "nudge"
    if stage == _STAGE_OWNER:
        owner_inbox.add(
            f"{profile_id} has been inactive for {days:.0f} days.",
            kind="dropoff",
        )
        _maybe_email_owner(profile_id, days, owner_email)
        audit.log("dropoff_owner_notified", profile_id=profile_id,
                  details=f"{days:.0f}d inactive")
        return "owner_notify"
    if stage == _STAGE_PAUSE:
        for source in sync_orchestrator.SOURCES:
            user_prefs.set_auto_sync(source, False, store)
        audit.log("dropoff_sync_paused", profile_id=profile_id,
                  details=f"{days:.0f}d inactive — auto-sync paused")
        return "auto_pause"
    return "none"


def _maybe_email_owner(profile_id: str, days: float, owner_email: str | None) -> None:
    if not owner_email:
        return
    try:
        from modules import notifications
        if notifications.is_configured():
            body = (f"{profile_id} has not used Protocōl in {days:.0f} days.\n\n"
                    "Consider a personal check-in.")
            notifications.send_email(
                owner_email, "Protocōl — beta user drop-off", f"<p>{body}</p>", body
            )
    except Exception:
        pass


def evaluate_profile(profile_id: str, now: datetime | None = None,
                     owner_email: str | None = None) -> DropoffAction:
    """Evaluate one profile and apply any newly-warranted drop-off stage.

    Owner is never nudged/paused. Each stage fires once per spell; activity
    resets the spell.
    """
    now = now or _now()
    store = _store_for(profile_id)
    days = days_inactive(profile_id, now)

    if profile_id == OWNER_PROFILE_ID or days is None:
        return DropoffAction(profile_id, days or 0.0, 0, "none")

    target = stage_for(days)
    already = int(user_prefs.get("dropoff_stage_actioned", 0, store) or 0)

    # User is active again → clear the spell + any pending nudge.
    if target == 0:
        if already != 0:
            user_prefs.set_value("dropoff_stage_actioned", 0, store)
            user_prefs.set_value("dropoff_nudge", None, store)
        return DropoffAction(profile_id, days, 0, "none")

    if target <= already:
        return DropoffAction(profile_id, days, target, "none")

    action = _apply_stage(profile_id, days, target, store, owner_email)
    user_prefs.set_value("dropoff_stage_actioned", target, store)
    return DropoffAction(profile_id, days, target, action)


def run(allowlist=None, now: datetime | None = None) -> list[DropoffAction]:
    """Evaluate every allowlisted profile. Returns the actions taken."""
    from auth import load_allowlist

    now = now or _now()
    owner_email = (load_allowlist().get("owner") or {}).get("email")
    actions: list[DropoffAction] = []
    for pid in sync_orchestrator._enabled_profiles(allowlist):
        try:
            actions.append(evaluate_profile(pid, now=now, owner_email=owner_email))
        except Exception:
            actions.append(DropoffAction(pid, 0.0, 0, "none"))
    return actions
