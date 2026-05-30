"""v3.2 — consent capture + owner-visibility gating.

Each beta user has a ``consent.json`` in their profile dir recording:
- ``privacy_accepted_at`` — required acceptance of the privacy notice
- ``owner_visibility_consent`` (+ timestamp) — optional opt-in letting Ryan
  view their dashboard read-only
- ``revoked_at`` — set (not deleted) when the user revokes owner visibility

Revocation is timestamped rather than destructive so the audit trail is intact.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import audit
from storage import ProfileStorage


CONSENT_FILE = "consent.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {
        "privacy_accepted_at": None,
        "owner_visibility_consent": False,
        "owner_visibility_consent_at": None,
        "revoked_at": None,
    }


def load_consent(store: ProfileStorage | None = None) -> dict[str, Any]:
    store = store or ProfileStorage()
    data = store.read_json(CONSENT_FILE, default={})
    if not isinstance(data, dict) or not data:
        return _empty()
    base = _empty()
    base.update(data)
    return base


def has_accepted_privacy(store: ProfileStorage | None = None) -> bool:
    return bool(load_consent(store).get("privacy_accepted_at"))


def owner_can_view(store: ProfileStorage | None = None) -> bool:
    """True only if the user opted in AND has not since revoked."""
    c = load_consent(store)
    return bool(c.get("owner_visibility_consent")) and not c.get("revoked_at")


def record_consent(privacy_accepted: bool, owner_visibility: bool,
                   store: ProfileStorage | None = None) -> dict[str, Any]:
    """Persist the one-time consent screen choices."""
    store = store or ProfileStorage()
    now = _now()
    c = load_consent(store)
    if privacy_accepted and not c.get("privacy_accepted_at"):
        c["privacy_accepted_at"] = now
    if owner_visibility:
        c["owner_visibility_consent"] = True
        c["owner_visibility_consent_at"] = now
        c["revoked_at"] = None
    else:
        c["owner_visibility_consent"] = False
    store.write_json(CONSENT_FILE, c)
    audit.log("consent_granted", profile_id=store.profile_id,
              details=f"owner_visibility={owner_visibility}")
    return c


def set_owner_visibility(consent: bool, store: ProfileStorage | None = None) -> dict[str, Any]:
    """Toggle owner-visibility from the Settings page. Revocation is timestamped."""
    store = store or ProfileStorage()
    now = _now()
    c = load_consent(store)
    if consent:
        c["owner_visibility_consent"] = True
        c["owner_visibility_consent_at"] = now
        c["revoked_at"] = None
        audit.log("consent_granted", profile_id=store.profile_id, details="owner_visibility=True")
    else:
        c["owner_visibility_consent"] = False
        c["revoked_at"] = now
        audit.log("consent_revoked", profile_id=store.profile_id, details="owner_visibility=False")
    store.write_json(CONSENT_FILE, c)
    return c
