"""Deterministic rule engine for the 14 Tier-1 biomarker explainers.

Per spec 2.4, the *personalized interpretation* of a biomarker is computed by
this engine — NOT by the LLM. The LLM is only ever called to wrap the
structured dict below in friendly prose, and must not introduce new clinical
facts. Because the engine is pure and deterministic, regenerating an explainer
yields identical key facts (status/value/range/trend) every time.

Output schema (per spec 2.4)::

    {
      "biomarker": "apob_mg_dl",
      "label": "ApoB",
      "status": "above_optimal",   # within_optimal|above_optimal|flag_high|flag_low|no_data
      "user_value": 95,
      "unit": "mg/dL",
      "optimal_range": [40, 70],
      "lab_range": [40, 125],
      "trend_direction": "rising", # rising|falling|flat|unknown
      "trend_velocity_per_quarter": 5.0,
      "quarters_to_threshold": 3,
      "recommendation_tags": ["dietary_review", ...]
    }
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


_REF_PATH = Path(__file__).resolve().parents[2] / "reference" / "biomarker_reference.json"


def _load_reference() -> dict[str, dict[str, Any]]:
    with _REF_PATH.open() as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if not k.startswith("_")}


# The 14 Tier-1 biomarker explainers (spec 2.2 entries 1-14). Maps the chart-
# level explainer to the canonical biomarker key + a friendly label and the
# recommendation tags surfaced when the marker is out of optimal range.
TIER1_BIOMARKERS: dict[str, dict[str, Any]] = {
    "apob": {
        "canonical": "apob_mg_dl", "label": "ApoB",
        "high_tags": ["dietary_review", "consider_pcsk9_discussion", "recheck_lipid_panel"],
        "low_tags": [],
    },
    "lp_a": {
        "canonical": "lp_a_nmol_l", "label": "Lp(a)",
        "high_tags": ["genetic_risk_marker", "aggressive_apob_target"],
        "low_tags": [],
        "once_ever": True,
    },
    "hematocrit": {
        "canonical": "hematocrit_pct", "label": "Hematocrit",
        "high_tags": ["trt_polycythemia_review", "hydration_check", "consider_phlebotomy_discussion"],
        "low_tags": ["iron_panel_review"],
    },
    "alt_ast": {
        "canonical": "alt_u_l", "label": "ALT/AST",
        "high_tags": ["hepatic_review", "alcohol_review", "recheck_liver_panel"],
        "low_tags": [],
    },
    "ggt": {
        "canonical": "ggt_u_l", "label": "GGT",
        "high_tags": ["alcohol_review", "hepatic_oxidative_stress"],
        "low_tags": [],
    },
    "estradiol": {
        "canonical": "estradiol_pg_ml", "label": "Sensitive Estradiol (LC-MS)",
        "high_tags": ["ai_dose_review", "aromatization_review"],
        "low_tags": ["estradiol_too_low_review"],
    },
    "testosterone_total": {
        "canonical": "testosterone_total_ng_dl", "label": "Total Testosterone (trough)",
        "high_tags": ["dose_review_high"],
        "low_tags": ["trough_timing_review", "dose_review_low"],
    },
    "testosterone_free": {
        "canonical": "testosterone_free_pg_ml", "label": "Free Testosterone (dialysis)",
        "high_tags": ["dose_review_high"],
        "low_tags": ["shbg_review", "dose_review_low"],
    },
    "shbg": {
        "canonical": "shbg_nmol_l", "label": "SHBG",
        "high_tags": ["free_t_impact_review"],
        "low_tags": ["insulin_resistance_review"],
    },
    "hba1c": {
        "canonical": "hba1c_pct", "label": "HbA1c",
        "high_tags": ["glycemic_control_review", "cgm_correlation"],
        "low_tags": [],
    },
    "fasting_insulin": {
        "canonical": "fasting_insulin_uiu_ml", "label": "Fasting Insulin + HOMA-IR",
        "high_tags": ["insulin_resistance_review", "carb_timing_review"],
        "low_tags": [],
    },
    "igf_1": {
        "canonical": "igf_1_ng_ml", "label": "IGF-1",
        "high_tags": ["longevity_tradeoff_review"],
        "low_tags": ["gh_axis_review"],
    },
    "hscrp": {
        "canonical": "hscrp_mg_l", "label": "hs-CRP",
        "high_tags": ["inflammation_review", "infection_rule_out", "recheck_in_6wk"],
        "low_tags": [],
    },
    "egfr": {
        "canonical": "egfr_ml_min", "label": "Cystatin C-based eGFR",
        "high_tags": [],
        "low_tags": ["renal_function_review", "recheck_cystatin_c"],
    },
}


def _quarters_to_threshold(value: float, velocity_per_q: float,
                           low: float, high: float) -> int | None:
    """Whole quarters until the value crosses the nearer optimal bound, given a
    constant per-quarter velocity. ``None`` if it isn't heading toward a bound."""
    if velocity_per_q == 0:
        return None
    if velocity_per_q > 0:  # rising → distance to the high bound
        if value >= high:
            return 0
        remaining = high - value
        return max(1, int(remaining / velocity_per_q + 0.999))
    else:  # falling → distance to the low bound
        if value <= low:
            return 0
        remaining = value - low
        return max(1, int(remaining / abs(velocity_per_q) + 0.999))


def _status(value: float, opt_low: float, opt_high: float,
            lab_low: float, lab_high: float) -> str:
    if lab_low is not None and value < lab_low:
        return "flag_low"
    if lab_high is not None and value > lab_high:
        return "flag_high"
    if opt_low <= value <= opt_high:
        return "within_optimal"
    if value > opt_high:
        return "above_optimal"
    return "below_optimal"


def evaluate(biomarker_id: str, series: pd.DataFrame | None,
             value_col: str = "value", date_col: str = "date") -> dict[str, Any]:
    """Run the deterministic rule engine for one Tier-1 biomarker.

    ``series`` is the user's history for this marker (already filtered to the
    one biomarker), with a value column and a date column. Returns the schema
    documented at the top of this module. Pure + deterministic.
    """
    spec = TIER1_BIOMARKERS.get(biomarker_id)
    if spec is None:
        raise KeyError(f"unknown Tier-1 biomarker: {biomarker_id}")

    ref = _load_reference().get(spec["canonical"], {})
    opt_low = ref.get("optimal_low")
    opt_high = ref.get("optimal_high")
    lab_low = ref.get("lab_low")
    lab_high = ref.get("lab_high")
    unit = ref.get("unit", "")

    base: dict[str, Any] = {
        "biomarker": spec["canonical"],
        "label": spec["label"],
        "unit": unit,
        "optimal_range": [opt_low, opt_high],
        "lab_range": [lab_low, lab_high],
        "trend_direction": "unknown",
        "trend_velocity_per_quarter": None,
        "quarters_to_threshold": None,
        "recommendation_tags": [],
    }

    if series is None or len(series) == 0 or value_col not in series.columns:
        base["status"] = "no_data"
        base["user_value"] = None
        return base

    df = series.dropna(subset=[value_col]).copy()
    if df.empty:
        base["status"] = "no_data"
        base["user_value"] = None
        return base

    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.sort_values(date_col)

    latest_value = float(df[value_col].iloc[-1])
    base["user_value"] = latest_value
    base["status"] = _status(latest_value, opt_low, opt_high, lab_low, lab_high)

    # Trend: per-quarter velocity from first→last over the elapsed quarters.
    if len(df) >= 2 and date_col in df.columns and df[date_col].notna().all():
        first_v = float(df[value_col].iloc[0])
        days = (df[date_col].iloc[-1] - df[date_col].iloc[0]).days
        quarters = max(days / 91.3125, 0.0)
        if quarters > 0:
            velocity = round((latest_value - first_v) / quarters, 2)
            base["trend_velocity_per_quarter"] = velocity
            if velocity > 0.0:
                base["trend_direction"] = "rising"
            elif velocity < 0.0:
                base["trend_direction"] = "falling"
            else:
                base["trend_direction"] = "flat"
            if opt_low is not None and opt_high is not None:
                base["quarters_to_threshold"] = _quarters_to_threshold(
                    latest_value, velocity, opt_low, opt_high
                )
        else:
            base["trend_direction"] = "flat"
            base["trend_velocity_per_quarter"] = 0.0
    elif len(df) >= 2:
        base["trend_direction"] = "flat"

    # Recommendation tags keyed off status.
    if base["status"] in ("above_optimal", "flag_high"):
        base["recommendation_tags"] = list(spec.get("high_tags", []))
    elif base["status"] in ("below_optimal", "flag_low"):
        base["recommendation_tags"] = list(spec.get("low_tags", []))

    return base
