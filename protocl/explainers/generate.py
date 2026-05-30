"""v3.3 — tier generators that turn data into explanation text.

Tier 1: static educational. For the 14 biomarkers, the *personalized* facts
        come from the deterministic rules engine; the LLM only wraps tone. For
        non-biomarker surfaces, Tier 1 is a static educational blurb.
Tier 2: personalized interpretation of the user's chart data.
Tier 3: on-demand chat answering a user question about the chart.

All three route through ``llm.complete`` (which enforces PII-free prompts) and
the cache decorators. Cost + rate-limit accounting happens in ``run_tier``.
"""
from __future__ import annotations

from typing import Any

from explainers import cache, llm, rate_limit, registry
from explainers.rules import TIER1_BIOMARKERS, evaluate


# ── Static educational copy for non-biomarker surfaces (Tier 1) ─────────────
_STATIC_TIER1: dict[str, str] = {
    "sleep_score_trend": "Your sleep score blends duration, stages, and disturbances into one 0–100 number. The 30/90-day rolling averages smooth nightly noise so you can see real direction.",
    "sleep_stage_breakdown": "Sleep cycles through light, deep, and REM stages. Deep sleep drives physical recovery; REM supports memory and mood. Most adults target ~1.5–2h of each.",
    "sleep_consistency": "Going to bed and waking at consistent times stabilizes your circadian rhythm. Bedtime variance is one of the strongest predictors of next-day readiness.",
    "hrv_vs_sleep_score": "Heart-rate variability reflects autonomic recovery. Higher HRV on well-slept nights is expected; a persistent decoupling can flag stress or under-recovery.",
    "rhr_vs_sleep_quality": "Resting heart rate typically falls on high-quality sleep nights. A rising RHR alongside poor sleep can indicate illness, alcohol, or overtraining.",
    "sleep_debt_cumulative": "Sleep debt accumulates when nightly sleep falls short of your need. Cumulative debt is paid down with extra sleep, not a single long night.",
    "active_alerts_summary": "Active alerts flag biomarkers or behaviors that crossed a threshold. Critical alerts warrant near-term action; warnings are worth monitoring.",
    "alert_frequency_by_category": "Grouping alerts by category shows where your system is under the most strain over time — e.g. recurring lipid vs liver vs glycemic alerts.",
    "oor_heatmap": "The out-of-range heatmap shows which biomarkers sit outside optimal across draws. Clusters in one panel point to a system worth a focused review.",
    "trend_velocity_table": "Trend velocity ranks markers by how fast they're moving per quarter, so you can act on the fastest movers before they cross a threshold.",
    "inbody_trend": "InBody segmental analysis tracks lean mass, fat mass, and body-fat percentage. Trends matter more than any single scan, which is sensitive to hydration.",
    "training_volume_by_week": "Weekly training volume (duration or load) shows whether you're progressively overloading, maintaining, or detraining.",
    "strava_power_hr_trend": "Power-to-HR (aerobic decoupling) over time is a window into aerobic fitness: the same power at a lower HR signals improving efficiency.",
    "recovery_score": "Recovery score blends HRV, RHR, and sleep into a readiness signal for how hard to train today.",
    "supplement_adherence": "Adherence tracks how consistently you take your protocol. Low adherence undermines the ability to attribute biomarker changes to a given intervention.",
    "trt_injection_timing": "Trough levels are measured just before the next dose. Comparing injection timing to trough testosterone/estradiol helps dial in protocol cadence.",
}


def _tier1_template(label: str) -> str:
    return (
        f"Rewrite the following structured facts about the biomarker '{label}' "
        "into 2-3 friendly, plain-language sentences for an expert user. Do NOT "
        "add any new numbers, ranges, or clinical claims beyond what is in the "
        "data. Refer to the person only as 'the user'."
    )


@cache.cached_explainer(tier=1)
def _tier1_llm(chart_id: str, data: Any) -> str:
    surface = registry.get(chart_id)
    label = (surface.title if surface else chart_id)
    text, _ = llm.complete(llm.build_prompt(_tier1_template(label), data),
                           model=llm.MODEL_TIER12, max_tokens=220)
    return llm.with_disclaimer(text)


def tier1(chart_id: str, biomarker_data: dict | None = None) -> str:
    """Tier 1 educational text. Biomarker surfaces wrap the rules-engine facts;
    other surfaces return static educational copy + disclaimer."""
    surface = registry.get(chart_id)
    if surface and surface.tier1_biomarker:
        # Rules-engine facts are deterministic; LLM only wraps tone (and is
        # cached). If no key configured, return a deterministic sentence.
        facts = biomarker_data or {}
        if not llm.base_llm.is_configured():
            return llm.with_disclaimer(_deterministic_sentence(facts))
        return _tier1_llm(chart_id, facts)
    blurb = _STATIC_TIER1.get(chart_id, "This chart visualizes one of your tracked health signals over time.")
    return llm.with_disclaimer(blurb)


def _deterministic_sentence(facts: dict) -> str:
    """A no-LLM fallback sentence built purely from rule-engine facts."""
    if not facts or facts.get("status") == "no_data":
        return "No data yet for this biomarker — add a lab draw to see your interpretation."
    label = facts.get("label", "This marker")
    val = facts.get("user_value")
    unit = facts.get("unit", "")
    lo, hi = (facts.get("optimal_range") or [None, None])
    status = facts.get("status", "").replace("_", " ")
    trend = facts.get("trend_direction", "unknown")
    return (f"{label} is {val} {unit} ({status}); optimal is {lo}–{hi} {unit}. "
            f"Recent trend: {trend}.")


# ── Tier 2: personalized interpretation ─────────────────────────────────────
_TIER2_TEMPLATE = (
    "Interpret the following chart data for the user in 3-5 sentences. "
    "Describe what the data shows and the direction of the trend. Reference "
    "only the numbers provided; do not invent values or give medical advice. "
    "Refer to the person only as 'the user'."
)


@cache.cached_explainer(tier=2)
def _tier2_llm(chart_id: str, data: Any, *, store=None) -> str:
    text, usage = llm.complete(llm.build_prompt(_TIER2_TEMPLATE, data),
                               model=llm.MODEL_TIER12, max_tokens=400)
    _account(store, chart_id, tier=2, model=llm.MODEL_TIER12, usage=usage)
    return llm.with_disclaimer(text)


def tier2(chart_id: str, data: Any, *, store=None) -> str:
    return _tier2_llm(chart_id, data, store=store)


# ── Tier 3: on-demand chat (never cached) ───────────────────────────────────

def tier3(chart_id: str, data: Any, question: str, *, store=None) -> str:
    template = (
        "Answer the user's question about this chart using only the data "
        "provided. If the data can't answer it, say so. No medical advice. "
        f"Refer to the person only as 'the user'.\n\nQUESTION: {question}"
    )
    text, usage = llm.complete(llm.build_prompt(template, data),
                               model=llm.MODEL_TIER3, max_tokens=500)
    _account(store, chart_id, tier=3, model=llm.MODEL_TIER3, usage=usage)
    return llm.with_disclaimer(text)


def _account(store, chart_id: str, *, tier: int, model: str, usage: dict) -> None:
    """Record an uncached generation against rate limits + cost log."""
    if store is None:
        from storage import ProfileStorage
        store = ProfileStorage()
    rate_limit.record_generation(store, tier)
    rate_limit.log_cost(store.profile_id, chart_id, tier, model,
                        usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def biomarker_facts(chart_id: str, series) -> dict:
    """Run the deterministic rule engine for a biomarker surface."""
    surface = registry.get(chart_id)
    if not surface or not surface.tier1_biomarker:
        return {}
    return evaluate(surface.tier1_biomarker, series)
