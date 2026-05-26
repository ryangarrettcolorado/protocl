"""Top-nav builder — reads page_registry.json + user preferences.

Builds an ordered ``{group_label: [st.Page, ...]}`` dict and hands it to
``st.navigation(position="top")``. Pages hidden via Settings are filtered
before the dict is constructed. The Settings page is always included.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from modules.preferences import load_preferences, visible_page_ids


REGISTRY_PATH = Path(__file__).resolve().parent.parent / "reference" / "page_registry.json"


# ────────────────────────────────────────────────────────────────────────────
# Registry I/O
# ────────────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_registry() -> dict[str, Any]:
    """Load and lightly validate the page registry."""
    with REGISTRY_PATH.open() as f:
        reg = json.load(f)
    reg.setdefault("groups", [])
    reg.setdefault("pages", [])
    return reg


def all_page_ids() -> list[str]:
    """All registered page ids, in registry order."""
    return [p["id"] for p in load_registry().get("pages", [])]


def page_meta(page_id: str) -> dict[str, Any] | None:
    for p in load_registry().get("pages", []):
        if p["id"] == page_id:
            return p
    return None


def group_meta(group_id: str) -> dict[str, Any] | None:
    for g in load_registry().get("groups", []):
        if g["id"] == group_id:
            return g
    return None


def group_label(group_id: str) -> str:
    g = group_meta(group_id) or {}
    icon = g.get("icon", "").strip()
    label = g.get("label", group_id.replace("_", " ").title())
    return f"{icon} {label}".strip()


# ────────────────────────────────────────────────────────────────────────────
# Cross-page link helper
# ────────────────────────────────────────────────────────────────────────────

def page_link(page_id: str, *, label: str | None = None, icon: str | None = None,
              use_container_width: bool = False) -> None:
    """Render an ``st.page_link`` for a registered page id.

    Centralizing this means we can rename files freely as long as the
    registry stays in sync. Falls back silently to a label-only caption
    when the page id is unknown.
    """
    meta = page_meta(page_id)
    if meta is None:
        st.caption(label or page_id)
        return
    st.page_link(
        meta["module"],
        label=label or meta["title"],
        icon=icon or meta.get("icon"),
        use_container_width=use_container_width,
    )


# ────────────────────────────────────────────────────────────────────────────
# Navigation builder
# ────────────────────────────────────────────────────────────────────────────

def build_navigation():
    """Return ``st.navigation(...)`` with five collapsible top-nav groups.

    Reads the registry, filters pages by user-preferred visibility, and
    constructs an ordered dict mapping group labels to lists of ``st.Page``.
    """
    reg = load_registry()
    prefs = load_preferences()
    visible = visible_page_ids(prefs)

    # Order groups by their .order field.
    groups_ordered = sorted(reg["groups"], key=lambda g: g.get("order", 99))

    # Order pages within each group.
    pages_by_group: dict[str, list[dict[str, Any]]] = {g["id"]: [] for g in groups_ordered}
    for p in sorted(reg["pages"], key=lambda p: p.get("order", 99)):
        if p["id"] not in visible:
            continue
        bucket = pages_by_group.setdefault(p["group"], [])
        bucket.append(p)

    nav_dict: dict[str, list[Any]] = {}
    home_page = None
    for g in groups_ordered:
        page_objs: list[Any] = []
        for p in pages_by_group.get(g["id"], []):
            module_path = p["module"]
            # Resolve relative to repo root (where app.py lives).
            page_obj = st.Page(
                module_path,
                title=p["title"],
                icon=p.get("icon"),
                url_path=p["id"],
                default=(p["id"] == "home"),
            )
            page_objs.append(page_obj)
            if p["id"] == "home":
                home_page = page_obj
        if page_objs:
            nav_dict[group_label(g["id"])] = page_objs

    # Guarantee home is reachable even if a user hid it (shouldn't happen
    # via Settings UI, but defensive against a hand-edited prefs file).
    if home_page is None:
        home_meta = page_meta("home")
        if home_meta is not None:
            fallback_home = st.Page(
                home_meta["module"],
                title=home_meta["title"],
                icon=home_meta.get("icon"),
                url_path="home",
                default=True,
            )
            today_label = group_label("today")
            nav_dict.setdefault(today_label, []).insert(0, fallback_home)

    return st.navigation(nav_dict, position="top")
