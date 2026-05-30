"""v3.3 AI Explainers package.

Three-tier explainer system (spec 2.1):
- Tier 1 — static educational (deterministic rules + cached LLM tone wrapper)
- Tier 2 — personalized interpretation (per-user cached LLM)
- Tier 3 — on-demand chat (uncached, rate-limited)

Public surface used by pages:
    from explainers.ui import explainer_block
"""
from __future__ import annotations
