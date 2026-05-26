"""User preferences — load, save, persona apply, page-visibility helpers.

v1.5 stays on the local file backend. Preferences live in
``data/<user>/user_preferences.json`` and are seeded from
``data/templates/user_preferences.template.json`` on first run.

Every public accessor uses ``.get()`` with defaults so a missing or
truncated preferences file never crashes the app.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TEMPLATE_PATH = DATA_DIR / "templates" / "user_preferences.template.json"
DEFAULT_USER = "ryan"


# ────────────────────────────────────────────────────────────────────────────
# Persona presets — keyed by the canonical persona ids in the spec.
# Each persona applies (a) a visible_pages list and (b) a pinned_biomarkers
# list to Home Row 4. Persona "custom" leaves whatever the user already set.
# ────────────────────────────────────────────────────────────────────────────

PERSONA_PRESETS: dict[str, dict[str, Any]] = {
    "performance": {
        "visible_pages": [
            "home", "action_items", "daily_trackers",
            "bloodwork", "body_composition", "cgm_glucose", "wearables",
            "training_activity", "zone2_vo2max",
            "protocol", "nof1_experiments", "recommendations",
            "timeline", "imports", "settings",
        ],
        "pinned_biomarkers": [
            "apob_mg_dl", "hscrp_mg_l", "testosterone_free_pg_ml",
            "vo2_max_ml_kg_min", "body_fat_pct",
        ],
    },
    "longevity": {
        "visible_pages": [
            "home", "action_items", "daily_trackers",
            "bloodwork", "body_composition", "cgm_glucose", "wearables",
            "biological_age",
            "training_activity", "zone2_vo2max",
            "protocol", "nof1_experiments", "recommendations", "risks_alerts",
            "clinician_summary", "timeline", "imports", "settings",
        ],
        "pinned_biomarkers": [
            "apob_mg_dl", "hba1c_pct", "lp_a_nmol_l",
            "hscrp_mg_l", "vitamin_d_ng_ml",
        ],
    },
    "clinical": {
        "visible_pages": [
            "home", "action_items", "daily_trackers",
            "bloodwork", "body_composition", "cgm_glucose", "wearables",
            "biological_age",
            "protocol", "recommendations", "risks_alerts", "clinician_summary",
            "timeline", "imports", "settings",
        ],
        "pinned_biomarkers": [
            "apob_mg_dl", "hba1c_pct", "egfr_ml_min", "alt_u_l", "hscrp_mg_l",
        ],
    },
    "custom": {},
}


# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────

def _prefs_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / "user_preferences.json"


def _load_template() -> dict[str, Any]:
    if not TEMPLATE_PATH.exists():
        # Last-ditch defaults if the template file is missing.
        return {
            "schema_version": 1,
            "profile": {},
            "persona": "custom",
            "visible_pages": [],
            "home_layout": {
                "rows_visible": ["status", "alerts", "attention", "trends",
                                 "changes", "recommendations", "clinician"],
                "row_order":    ["status", "alerts", "attention", "trends",
                                 "changes", "recommendations", "clinician"],
                "pinned_biomarkers": [],
            },
            "ranges": {"default_view": "overlay", "personal_targets": {}},
            "appearance": {"theme": "dark", "accent_color": "gold", "density": "comfortable"},
            "notifications_v2_stub": {},
            "_meta": {"created_at": None, "updated_at": None},
        }
    with TEMPLATE_PATH.open() as f:
        return json.load(f)


# ────────────────────────────────────────────────────────────────────────────
# Init / load / save
# ────────────────────────────────────────────────────────────────────────────

def ensure_initialized(user_id: str = DEFAULT_USER) -> None:
    """Create the user preferences file from the template if it doesn't exist."""
    path = _prefs_path(user_id)
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _load_template()
    now = datetime.now(timezone.utc).isoformat()
    payload.setdefault("_meta", {})
    payload["_meta"]["created_at"] = now
    payload["_meta"]["updated_at"] = now
    with path.open("w") as f:
        json.dump(payload, f, indent=2)


@st.cache_data(ttl=60)
def load_preferences(user_id: str = DEFAULT_USER) -> dict[str, Any]:
    """Load preferences as a dict. Falls back to the template on any error.

    Cached briefly so widgets don't hammer the file each rerun. ``save_preferences``
    clears the cache so a write is immediately visible.
    """
    path = _prefs_path(user_id)
    if not path.exists():
        return _load_template()
    try:
        with path.open() as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _load_template()


def save_preferences(prefs: dict[str, Any], user_id: str = DEFAULT_USER) -> None:
    """Atomically overwrite the preferences file and refresh the cache."""
    path = _prefs_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    prefs = copy.deepcopy(prefs)
    prefs.setdefault("_meta", {})
    prefs["_meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    prefs["_meta"].setdefault("created_at", prefs["_meta"]["updated_at"])
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump(prefs, f, indent=2)
    tmp.replace(path)
    # Invalidate load_preferences cache so the next reader sees the new state.
    load_preferences.clear()


# ────────────────────────────────────────────────────────────────────────────
# Persona logic
# ────────────────────────────────────────────────────────────────────────────

def apply_persona(persona: str, prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a copy of ``prefs`` with the persona preset applied (not saved).

    "custom" leaves the user's existing visible_pages / pins untouched.
    Unknown persona ids fall through silently as "custom".
    """
    prefs = copy.deepcopy(prefs) if prefs is not None else load_preferences()
    preset = PERSONA_PRESETS.get(persona, {})
    prefs["persona"] = persona

    if preset:
        visible = list(preset.get("visible_pages", prefs.get("visible_pages", [])))
        # Settings must always be reachable.
        if "settings" not in visible:
            visible.append("settings")
        prefs["visible_pages"] = visible

        pinned = preset.get("pinned_biomarkers")
        if pinned is not None:
            prefs.setdefault("home_layout", {})
            prefs["home_layout"]["pinned_biomarkers"] = list(pinned)

    return prefs


# ────────────────────────────────────────────────────────────────────────────
# Accessors used by nav.py, home_dashboard.py, and page modules
# ────────────────────────────────────────────────────────────────────────────

def visible_page_ids(prefs: dict[str, Any] | None = None) -> set[str]:
    """Return the set of page ids that should appear in the nav."""
    prefs = prefs if prefs is not None else load_preferences()
    visible = set(prefs.get("visible_pages", []))
    visible.add("settings")  # never hidable
    return visible


def is_page_visible(page_id: str, prefs: dict[str, Any] | None = None) -> bool:
    return page_id in visible_page_ids(prefs)


def pinned_biomarkers(prefs: dict[str, Any] | None = None) -> list[str]:
    prefs = prefs if prefs is not None else load_preferences()
    return list(prefs.get("home_layout", {}).get("pinned_biomarkers", []))


def home_rows_visible(prefs: dict[str, Any] | None = None) -> list[str]:
    prefs = prefs if prefs is not None else load_preferences()
    layout = prefs.get("home_layout", {}) or {}
    rows = list(layout.get("rows_visible") or [])
    # Rows 1–3 (status / alerts / attention) are always on per spec §8.3.
    for required in ("status", "alerts", "attention"):
        if required not in rows:
            rows.insert(0, required)
    return rows


def home_row_order(prefs: dict[str, Any] | None = None) -> list[str]:
    prefs = prefs if prefs is not None else load_preferences()
    layout = prefs.get("home_layout", {}) or {}
    default = ["status", "alerts", "attention", "trends",
               "changes", "recommendations", "clinician"]
    order = list(layout.get("row_order") or default)
    # Ensure all default rows are present somewhere so a corrupt prefs file
    # never silently drops a critical row.
    for r in default:
        if r not in order:
            order.append(r)
    return order


def appearance(prefs: dict[str, Any] | None = None) -> dict[str, str]:
    prefs = prefs if prefs is not None else load_preferences()
    a = prefs.get("appearance") or {}
    return {
        "theme":        a.get("theme", "dark"),
        "accent_color": a.get("accent_color", "gold"),
        "density":      a.get("density", "comfortable"),
    }


def profile(prefs: dict[str, Any] | None = None) -> dict[str, Any]:
    prefs = prefs if prefs is not None else load_preferences()
    return dict(prefs.get("profile") or {})


def ranges_view(prefs: dict[str, Any] | None = None) -> str:
    prefs = prefs if prefs is not None else load_preferences()
    return (prefs.get("ranges") or {}).get("default_view", "overlay")


def personal_target(canonical: str, prefs: dict[str, Any] | None = None) -> dict[str, float] | None:
    """Return ``{low, high}`` if the user has set a personal target override."""
    prefs = prefs if prefs is not None else load_preferences()
    targets = (prefs.get("ranges") or {}).get("personal_targets") or {}
    return targets.get(canonical)
