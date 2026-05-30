# v3.3 — AI Explainers (Top 30 charts)

Every key chart in Protocōl carries an **"💡 Explain this chart"** block. The
system is built so the *facts* are deterministic and the LLM only ever rewrites
them into friendly prose — it never invents clinical claims — while PII never
leaves the app and cost is tightly bounded.

## The 30 surfaces

`explainers/registry.py` defines exactly 30 `ChartSurface` entries, each
mapping a stable `chart_id` → page → category → (for 14) a Tier-1 biomarker:

- **14 biomarkers** (bloodwork) — ApoB, Lp(a), Hematocrit, ALT/AST, GGT,
  Estradiol, Total & Free testosterone, SHBG, HbA1c, Fasting insulin, IGF-1,
  hs-CRP, eGFR.
- **6 sleep** — score trend, stage breakdown, consistency, HRV vs score,
  RHR vs quality, sleep-debt cumulative.
- **4 alerts/trends** — active alerts summary, alert frequency by category,
  out-of-range heatmap, trend-velocity table.
- **6 training/body-comp** — InBody trend, training volume by week, Strava
  power/HR, recovery score, supplement adherence, TRT injection timing.

The block is rendered by `explainers/ui.py::explainer_block(chart_id, ...)`,
called once below each chart.

## Three tiers

| Tier | Purpose | Model | Cache |
|------|---------|-------|-------|
| 1 | Educational ("what this is") | `gpt-4o-mini` | Global, 30-day TTL |
| 2 | Personalized ("your data") | `gpt-4o-mini` | Per-user, until `data_hash` changes |
| 3 | Free-form Q&A | `gpt-4o` | Never cached |

`gpt-4o` is **only** used for Tier 3 chat — never Tier 1/2 — for cost control.

## Deterministic rules engine (Tier 1 biomarkers)

`explainers/rules/` computes the *interpretation* of each Tier-1 biomarker —
not the LLM. `evaluate(biomarker_id, series)` returns a pure, deterministic
schema:

```json
{
  "biomarker": "apob_mg_dl", "label": "ApoB",
  "status": "above_optimal",          // within_optimal|above_optimal|below_optimal|flag_high|flag_low|no_data
  "user_value": 95, "unit": "mg/dL",
  "optimal_range": [40, 70], "lab_range": [40, 125],
  "trend_direction": "rising",        // rising|falling|flat|unknown
  "trend_velocity_per_quarter": 5.0,
  "quarters_to_threshold": 3,
  "recommendation_tags": ["dietary_review", ...]
}
```

Status/value/range/trend are identical on every regeneration. The LLM is given
only this dict to phrase; it cannot introduce new clinical facts.

## Data minimization

`explainers/llm.py`:

- `scrub_pii()` recursively strips PII keys (`email`, `name`, `display_name`,
  `profile_id`, …) and redacts any email-looking string.
- `assert_no_pii()` raises before any prompt is sent if it contains an email
  or a known session name/email.
- Prompts contain only the specific (scrubbed) chart data — never the full
  profile. The user is referenced to the model only as "the user."

## Cost control & rate limits

`explainers/rate_limit.py`:

- Per user/day: **50** Tier-2 generations, **10** Tier-3 questions
  (cached hits don't count).
- Per app/day: **500** total LLM calls. When exceeded, Tier 2/3 are disabled;
  Tier 1 cached content stays available.
- Token usage + estimated cost logged to `data/shared/llm_cost_log.csv`,
  surfaced on the owner-only **LLM Costs** admin page.

## Tests

- `test_explainer_rules.py` — 14 biomarkers, status thresholds, trend math,
  determinism, output schema.
- `test_explainer_cache.py` — `data_hash` stability, per-tier behavior, TTL,
  invalidation, decorator call-count.
- `test_rate_limits.py` — per-user + per-app limits, pricing, cost logging.
- `test_data_minimization.py` — PII scrubbing, prompt guards, model routing.
