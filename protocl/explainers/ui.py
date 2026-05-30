"""v3.3 — the uniform ``explainer_block`` rendered below each of the 30 charts.

Usage on a page::

    from explainers.ui import explainer_block
    st.plotly_chart(fig)
    explainer_block("apob_trend", chart_data=apob_df_for_llm, biomarker_series=apob_series)

The block is collapsed by default ("💡 Explain this chart"). On expand it shows
Tier 1 (educational), Tier 2 (personalized), and a Tier 3 "Ask a question"
input, with a disclaimer footer. Rate limits + the per-app budget gate Tier 2/3.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from explainers import generate, rate_limit, registry


def _budget_banner() -> bool:
    """Show the budget banner if the app ceiling is hit. Returns True if hit."""
    if rate_limit.app_budget_remaining() <= 0:
        st.info("Daily LLM budget reached — Tier 1 explanations remain available.")
        return True
    return False


def explainer_block(chart_id: str, *, chart_data: Any = None,
                    biomarker_series: Any = None) -> None:
    """Render the explainer expander beneath a chart.

    ``chart_data`` — the minimized data dict/records to interpret (Tier 2/3).
    ``biomarker_series`` — the raw history for a Tier-1 biomarker surface; the
    deterministic rules engine runs on it.
    """
    surface = registry.get(chart_id)
    title = surface.title if surface else chart_id

    with st.expander("💡 Explain this chart", expanded=False):
        facts = None
        if surface and surface.tier1_biomarker:
            facts = generate.biomarker_facts(chart_id, biomarker_series)

        # Tier 1 — always available (cached / deterministic).
        st.markdown("**What this is**")
        with st.spinner("Loading explanation…"):
            st.markdown(generate.tier1(chart_id, facts))

        if facts and facts.get("status") not in (None, "no_data"):
            st.caption(
                f"Status: **{facts['status'].replace('_', ' ')}** · "
                f"value {facts.get('user_value')} {facts.get('unit', '')} · "
                f"optimal {facts.get('optimal_range')} · trend {facts.get('trend_direction')}"
            )

        budget_hit = _budget_banner()

        # Tier 2 — personalized interpretation.
        from storage import ProfileStorage
        store = ProfileStorage()
        st.markdown("**Your data**")
        if chart_data is None:
            st.caption("No chart data available to personalize yet.")
        elif budget_hit or not rate_limit.can_generate(store, 2):
            st.caption("Personalized interpretation paused (daily limit reached).")
        else:
            if st.button("Generate personalized interpretation", key=f"t2_{chart_id}"):
                with st.spinner("Analyzing your data…"):
                    st.markdown(generate.tier2(chart_id, chart_data, store=store))

        # Tier 3 — ask a question.
        st.markdown("**Ask a question**")
        remaining3 = rate_limit.remaining(store, 3)
        if budget_hit or remaining3 <= 0:
            st.caption("Q&A paused (daily limit reached).")
        else:
            q = st.text_input("Ask about this chart", key=f"t3q_{chart_id}",
                              placeholder=f"e.g. Why is my {title} trending this way?")
            if st.button("Ask", key=f"t3_{chart_id}") and q.strip():
                with st.spinner("Thinking…"):
                    st.markdown(generate.tier3(chart_id, chart_data or {}, q, store=store))
            st.caption(f"{remaining3} questions left today.")
