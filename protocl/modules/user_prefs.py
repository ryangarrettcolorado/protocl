"""v3.5/v3.6 — per-profile preferences.json (auto-sync, changelog, analytics).

This is a thin, isolation-safe key/value store that lives at
``data/profiles/<profile_id>/preferences.json`` (the owner reuses
``data/ryan/preferences.json``). It is intentionally *separate* from the v1.5
``user_preferences.json`` persona/layout file so the two never collide.

Everything is read/written through :class:`storage.ProfileStorage`, so the
v3.2 per-profile isolation guarantee holds: page code can only ever touch the
current session's profile. The owner-side admin pages inspect another user's
preferences by constructing a ``ProfileStorage`` and re-pointing ``profile_id``
(the same owner-only pattern used in ``pages/30_admin_beta_overview.py``).

Keys
----
``auto_sync``                 ``{"strava": bool, "apple_health": bool}``
``last_seen_changelog_version`` latest changelog version the user has viewed
``changelog_banner_dismissed``  list of versions whose Home banner was dismissed
``analytics_consent``         opt-in for anonymized usage analytics (default on)
"""
from __future__ import annotations

from typing import Any

from storage import ProfileStorage, ReadOnlyError


PREFS_FILE = "preferences.json"


def _defaults() -> dict[str, Any]:
    return {
        "auto_sync": {"strava": False, "apple_health": False},
        "last_seen_changelog_version": None,
        "changelog_banner_dismissed": [],
        "analytics_consent": True,
        # v3.6 drop-off: a pending in-app nudge message (or None), and the
        # highest drop-off stage already actioned for this inactivity spell.
        "dropoff_nudge": None,
        "dropoff_stage_actioned": 0,
    }


def load(store: ProfileStorage | None = None) -> dict[str, Any]:
    """Load preferences merged over defaults (never raises on missing file)."""
    store = store or ProfileStorage()
    data = store.read_json(PREFS_FILE, default={})
    base = _defaults()
    if isinstance(data, dict):
        # Merge nested auto_sync so a partial file keeps both keys.
        auto = base["auto_sync"].copy()
        if isinstance(data.get("auto_sync"), dict):
            auto.update(data["auto_sync"])
        base.update(data)
        base["auto_sync"] = auto
    return base


def save(prefs: dict[str, Any], store: ProfileStorage | None = None) -> None:
    """Persist preferences. Silently skips when impersonating (read-only)."""
    store = store or ProfileStorage()
    try:
        store.write_json(PREFS_FILE, prefs)
    except ReadOnlyError:
        pass


def get(key: str, default: Any = None, store: ProfileStorage | None = None) -> Any:
    return load(store).get(key, default)


def set_value(key: str, value: Any, store: ProfileStorage | None = None) -> dict[str, Any]:
    store = store or ProfileStorage()
    prefs = load(store)
    prefs[key] = value
    save(prefs, store)
    return prefs


# ── auto-sync helpers ───────────────────────────────────────────────────────

def auto_sync_enabled(source: str, store: ProfileStorage | None = None) -> bool:
    return bool(load(store).get("auto_sync", {}).get(source, False))


def set_auto_sync(source: str, enabled: bool, store: ProfileStorage | None = None) -> dict[str, Any]:
    store = store or ProfileStorage()
    prefs = load(store)
    auto = dict(prefs.get("auto_sync") or {})
    auto[source] = bool(enabled)
    prefs["auto_sync"] = auto
    save(prefs, store)
    return prefs


# ── analytics consent helpers ───────────────────────────────────────────────

def analytics_allowed(store: ProfileStorage | None = None) -> bool:
    return bool(load(store).get("analytics_consent", True))


def set_analytics_consent(enabled: bool, store: ProfileStorage | None = None) -> dict[str, Any]:
    return set_value("analytics_consent", bool(enabled), store)
