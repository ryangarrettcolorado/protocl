"""Load biomarker reference ranges from /reference/biomarker_reference.json."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st


REF_PATH = Path(__file__).resolve().parent.parent / "reference" / "biomarker_reference.json"


@st.cache_data(ttl=300)
def load_reference() -> dict[str, dict[str, Any]]:
    """Return the full biomarker reference dict, excluding _meta."""
    with REF_PATH.open() as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def get(canonical: str) -> dict[str, Any] | None:
    """Look up a single biomarker reference entry."""
    return load_reference().get(canonical)


def panels() -> list[str]:
    """Return the unique panel names in canonical order."""
    seen, out = set(), []
    for entry in load_reference().values():
        p = entry.get("panel", "other")
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


PANEL_LABELS = {
    "lipids":             "Lipids",
    "liver":              "Liver",
    "kidney":             "Kidney",
    "hormones":           "Hormones",
    "thyroid":            "Thyroid",
    "glucose_insulin":    "Glucose & Insulin",
    "hematology":         "Hematology",
    "inflammation":       "Inflammation",
    "vitamins_minerals":  "Vitamins & Minerals",
    "cardiovascular":     "Cardiovascular",
    "other":              "Other",
}


def panel_label(panel: str) -> str:
    return PANEL_LABELS.get(panel, panel.replace("_", " ").title())
