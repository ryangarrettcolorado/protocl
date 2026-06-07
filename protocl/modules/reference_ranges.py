"""Backward-compatible reference range API.

This module preserves the original public surface used across the app
(``load_reference``, ``get``, ``panels``, ``panel_label``) while delegating
to the new :mod:`protocl.modules.biomarker_catalog` loader behind the scenes.

Pages and modules can migrate to the richer API at their own pace; nothing
breaks in the meantime.
"""
from __future__ import annotations

from typing import Any

try:
    import streamlit as st  # type: ignore

    _cache = st.cache_data(ttl=300)
except Exception:  # pragma: no cover - Streamlit not installed (tests)
    def _cache(fn):
        return fn

from . import biomarker_catalog


PANEL_LABELS = {
    "lipids":             "Lipids",
    "liver":              "Liver",
    "kidney":             "Kidney",
    "liver_kidney":       "Liver + Kidney",
    "hormones":           "Hormones",
    "thyroid":            "Thyroid",
    "glucose_insulin":    "Glucose & Insulin",
    "metabolic":          "Metabolic",
    "hematology":         "Hematology",
    "cbc":                "CBC",
    "inflammation":       "Inflammation",
    "vitamins_minerals":  "Vitamins & Minerals",
    "vitamins":           "Vitamins + Iron",
    "cardiovascular":     "Cardiovascular",
    "urinalysis":         "Urinalysis",
    "other":              "Other",
}


@_cache
def load_reference() -> dict[str, dict[str, Any]]:
    """Return the full biomarker reference dict keyed by canonical_key.

    Values mirror the legacy ``biomarker_reference.json`` shape so existing
    callers (``home_dashboard.py``, ``04_bloodwork.py``, etc.) keep working.
    """
    catalog = biomarker_catalog.load_catalog()
    out: dict[str, dict[str, Any]] = {}
    for marker in catalog.markers:
        out[marker.canonical_key] = marker.as_legacy_entry()
    return out


def get(canonical: str) -> dict[str, Any] | None:
    """Look up a single biomarker reference entry (legacy shape).

    Resolves both canonical keys and aliases.
    """
    catalog = biomarker_catalog.load_catalog()
    marker = catalog.get(canonical)
    return marker.as_legacy_entry() if marker else None


def panels() -> list[str]:
    """Return unique panel names in canonical order (legacy panel labels)."""
    seen, out = set(), []
    for entry in load_reference().values():
        p = entry.get("panel", "other")
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def panel_label(panel: str) -> str:
    return PANEL_LABELS.get(panel, panel.replace("_", " ").title())


# ---- New-style escape hatch ------------------------------------------------
#
# Callers that want the richer model (tri-band classification, aliases,
# tier-aware filtering, binary_flag handling) can import the catalog directly:
#
#     from protocl.modules.biomarker_catalog import load_catalog, Status
#     catalog = load_catalog()
#     status = catalog.classify("apob", 72)  # -> Status.OPTIMAL
#
# The shim above is here for the duration of the migration only.
