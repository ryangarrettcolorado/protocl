"""v3.3 — registry of the Top 30 explainer surfaces (spec 2.2).

Each entry maps a stable ``chart_id`` to the page it lives on, a human title,
the explainer tier mix it supports, and (for the 14 Tier-1 biomarkers) the
rule-engine ``biomarker_id`` from ``explainers.rules``.

``page`` values reference the page registry ids used by ``modules/nav.py`` /
``reference/page_registry.json`` so links stay stable across file renames.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChartSurface:
    chart_id: str
    title: str
    page: str            # page registry id (e.g. "bloodwork")
    page_module: str     # module path for st.page_link
    category: str        # biomarkers|sleep|alerts|training
    tier1_biomarker: str | None = None   # key into explainers.rules.TIER1_BIOMARKERS
    tiers: tuple[int, ...] = field(default=(1, 2, 3))


# spec 2.2 — exactly 30 surfaces, mapped to real pages in this codebase.
SURFACES: list[ChartSurface] = [
    # ── Biomarkers (Tier 1 priority — 14) ──────────────────────────────────
    ChartSurface("apob_trend", "ApoB trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "apob"),
    ChartSurface("lp_a_marker", "Lp(a) once-ever marker", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "lp_a"),
    ChartSurface("hematocrit_trend", "Hematocrit / Hemoglobin trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "hematocrit"),
    ChartSurface("alt_ast_trend", "ALT / AST trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "alt_ast"),
    ChartSurface("ggt_trend", "GGT trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "ggt"),
    ChartSurface("estradiol_trend", "Sensitive estradiol (LC-MS) trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "estradiol"),
    ChartSurface("testosterone_total_trough", "Total testosterone trough", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "testosterone_total"),
    ChartSurface("testosterone_free_trend", "Free testosterone (dialysis) trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "testosterone_free"),
    ChartSurface("shbg_trend", "SHBG trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "shbg"),
    ChartSurface("hba1c_trend", "HbA1c trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "hba1c"),
    ChartSurface("fasting_insulin_homa", "Fasting insulin + HOMA-IR", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "fasting_insulin"),
    ChartSurface("igf_1_trend", "IGF-1 trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "igf_1"),
    ChartSurface("hscrp_trend", "hs-CRP trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "hscrp"),
    ChartSurface("egfr_trend", "Cystatin C-based eGFR trend", "bloodwork", "pages/04_bloodwork.py", "biomarkers", "egfr"),

    # ── Sleep (v3.0 surfaces — 6) ───────────────────────────────────────────
    ChartSurface("sleep_score_trend", "Sleep score trend (rolling 30/90)", "sleep", "pages/20_sleep.py", "sleep"),
    ChartSurface("sleep_stage_breakdown", "Sleep stage breakdown", "sleep", "pages/20_sleep.py", "sleep"),
    ChartSurface("sleep_consistency", "Sleep consistency (bedtime variance)", "sleep", "pages/20_sleep.py", "sleep"),
    ChartSurface("hrv_vs_sleep_score", "HRV vs sleep score scatter", "sleep", "pages/20_sleep.py", "sleep"),
    ChartSurface("rhr_vs_sleep_quality", "RHR vs sleep quality", "sleep", "pages/20_sleep.py", "sleep"),
    ChartSurface("sleep_debt_cumulative", "Sleep debt cumulative", "sleep", "pages/20_sleep.py", "sleep"),

    # ── Alerts + Trends (v3.1 surfaces — 4) ─────────────────────────────────
    ChartSurface("active_alerts_summary", "Active alerts summary", "alerts", "pages/22_alerts.py", "alerts"),
    ChartSurface("alert_frequency_by_category", "Alert frequency by category", "alerts", "pages/22_alerts.py", "alerts"),
    ChartSurface("oor_heatmap", "Biomarker out-of-range heatmap", "risks_alerts", "pages/14_risks_alerts.py", "alerts"),
    ChartSurface("trend_velocity_table", "Trend velocity table (fastest movers)", "risks_alerts", "pages/14_risks_alerts.py", "alerts"),

    # ── Training + Body Comp (6) ─────────────────────────────────────────────
    ChartSurface("inbody_trend", "InBody body composition trend", "body_composition", "pages/05_body_composition.py", "training"),
    ChartSurface("training_volume_by_week", "Training volume by week", "training_activity", "pages/09_training_activity.py", "training"),
    ChartSurface("strava_power_hr_trend", "Strava power / HR trend", "strava_cycling", "pages/09b_strava_cycling.py", "training"),
    ChartSurface("recovery_score", "Recovery score", "wearables", "pages/07_wearables.py", "training"),
    ChartSurface("supplement_adherence", "Supplement adherence", "protocol", "pages/11_protocol.py", "training"),
    ChartSurface("trt_injection_timing", "TRT injection timing vs trough levels", "protocol", "pages/11_protocol.py", "training"),
]

_BY_ID: dict[str, ChartSurface] = {s.chart_id: s for s in SURFACES}


def get(chart_id: str) -> ChartSurface | None:
    return _BY_ID.get(chart_id)


def all_ids() -> list[str]:
    return [s.chart_id for s in SURFACES]


def tier1_ids() -> list[str]:
    return [s.chart_id for s in SURFACES if s.tier1_biomarker]


def by_category(category: str) -> list[ChartSurface]:
    return [s for s in SURFACES if s.category == category]


def as_dicts() -> list[dict[str, Any]]:
    return [s.__dict__ for s in SURFACES]
