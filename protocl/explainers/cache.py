"""v3.3 — explainer caching to control LLM cost (spec 2.5).

Cache key: ``(profile_id, chart_id, data_hash, tier)``.
``data_hash`` = SHA-256 of the JSON-serialized chart data.

Storage:
- Per-user: ``data/profiles/<profile_id>/explainer_cache.json``
- Tier 1 also has a global ``data/shared/tier1_explainer_cache.json`` (Tier 1
  is identical for every user, so it's shared and saves cost).

TTL: Tier 1 = 30 days; Tier 2 = infinite until ``data_hash`` changes; Tier 3 =
never cached.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

import storage


TIER1_TTL_SECONDS = 30 * 24 * 3600  # 30 days
USER_CACHE_FILE = "explainer_cache.json"
TIER1_GLOBAL_FILE = "tier1_explainer_cache.json"


def data_hash(data: Any) -> str:
    """SHA-256 of canonical JSON. Stable across dict ordering."""
    blob = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_key(profile_id: str, chart_id: str, dhash: str, tier: int) -> str:
    return f"{profile_id}::{chart_id}::{dhash}::t{tier}"


# ── Tier 1 global cache (shared across users) ───────────────────────────────

def _load_global() -> dict[str, Any]:
    path = storage.SHARED_DIR / TIER1_GLOBAL_FILE
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_global(data: dict[str, Any]) -> None:
    path = storage.shared_path(TIER1_GLOBAL_FILE)
    path.write_text(json.dumps(data, indent=2, default=str))


def get_tier1(chart_id: str, dhash: str) -> str | None:
    entry = _load_global().get(cache_key("_shared", chart_id, dhash, 1))
    if not entry:
        return None
    if time.time() - entry.get("ts", 0) > TIER1_TTL_SECONDS:
        return None
    return entry.get("text")


def set_tier1(chart_id: str, dhash: str, text: str) -> None:
    data = _load_global()
    data[cache_key("_shared", chart_id, dhash, 1)] = {"text": text, "ts": time.time()}
    _save_global(data)


# ── Per-user cache (Tier 2) ─────────────────────────────────────────────────

def _load_user(store: "storage.ProfileStorage") -> dict[str, Any]:
    return store.read_json(USER_CACHE_FILE, default={}) or {}


def get_user(store: "storage.ProfileStorage", chart_id: str, dhash: str, tier: int) -> str | None:
    entry = _load_user(store).get(cache_key(store.profile_id, chart_id, dhash, tier))
    # Tier 2 is infinite until data_hash changes, so no TTL check here.
    return entry.get("text") if entry else None


def set_user(store: "storage.ProfileStorage", chart_id: str, dhash: str, tier: int, text: str) -> None:
    data = _load_user(store)
    data[cache_key(store.profile_id, chart_id, dhash, tier)] = {"text": text, "ts": time.time()}
    try:
        store.write_json(USER_CACHE_FILE, data)
    except Exception:
        # read-only impersonation: don't persist, just skip
        pass


def clear_user(store: "storage.ProfileStorage") -> None:
    """Admin action: clear a single user's explainer cache."""
    try:
        store.write_json(USER_CACHE_FILE, {})
    except Exception:
        pass


def cached_explainer(tier: int) -> Callable:
    """Decorator wrapping a generator ``fn(chart_id, data, **kw) -> str``.

    Tier 1 reads/writes the global cache; Tier 2 the per-user cache; Tier 3 is
    never cached. The wrapped function is only invoked on a cache miss.
    """
    def deco(fn: Callable[..., str]) -> Callable[..., str]:
        def wrapper(chart_id: str, data: Any, *, store=None, **kw) -> str:
            dhash = data_hash(data)
            if tier == 1:
                hit = get_tier1(chart_id, dhash)
                if hit is not None:
                    return hit
                text = fn(chart_id, data, **kw)
                set_tier1(chart_id, dhash, text)
                return text
            if tier == 2:
                if store is None:
                    from storage import ProfileStorage
                    store = ProfileStorage()
                hit = get_user(store, chart_id, dhash, 2)
                if hit is not None:
                    return hit
                text = fn(chart_id, data, store=store, **kw)
                set_user(store, chart_id, dhash, 2, text)
                return text
            # Tier 3 — never cached.
            return fn(chart_id, data, **kw)
        wrapper.__wrapped__ = fn  # type: ignore[attr-defined]
        return wrapper
    return deco
