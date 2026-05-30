# Protocōl v2.0 — Decisions Log

Open architectural decisions and explicit deferrals from the v2.0 revision
sweep on branch `feat/protocl-v2-revisions`.

---

## Task Group 6 — Assessment-only findings

### 6A — Notifications (v2 preview)

**Current state.** A UI stub exists in **Settings → Notifications** that
persists user choices (channels, severity threshold, digest cadence) into
`user_preferences.json` under the key `notifications_v2_stub`. **No trigger
engine, no delivery, no dispatcher** — clicking "Save notification
preferences" only updates the JSON.

**What full implementation would require.**

1. **Trigger evaluation layer** — a rule engine that runs nightly (extending
   `scripts/daily_sync.py`) over the latest bloodwork draw, wearables roll,
   and protocol changes, emitting `events.jsonl` per user.
2. **Severity / debouncing** — same biomarker shouldn't re-fire daily; needs
   per-event "last-notified-at" state in a new `data/<user>/notifications.json`.
3. **Channel adapters.**
   - In-app: a `notifications` section on Home Row 2, already structurally
     there in `home_dashboard.py`.
   - Email: SendGrid or AWS SES integration; new `OPENAI_API_KEY`-style secret;
     template files for digest + critical alerts.
   - SMS: Twilio (~$0.01/message US). Requires phone number capture
     (now wired in 3F) and consent acknowledgement.
4. **Settings UI** completion — per-biomarker mute toggles, quiet hours.

**Credit estimate.** ~700–900 credits to ship the full path (trigger engine
~250, channel adapters ~250, settings polish ~150, testing/observability ~150).

**Recommendation.** Defer to v2.1. The current stub is honest — it says
"Coming in v2" — and the data model already captures user preferences so a
later trigger engine has somewhere to read from. **Not worth doing
half-way**; partial delivery (in-app only) would be confusing without
the digest + email backstops.

### 6B — Theme & Appearance

**Current state.** Settings exposes:
- **Theme:** `dark` / `light` / `system` — only `dark` is actually applied
  in CSS. `light` and `system` are persisted but ignored.
- **Accent color:** `gold` / `amber` / `cyan` — only `gold` flows into the
  `COLORS` palette in `modules/charts.py`; the other two persist but have
  no effect.
- **Density:** `comfortable` / `compact` — persisted, not wired.

**What completion would require.**

1. **Light theme** — invert the steel-dark palette in `theme.py` and add a
   `--theme: light/dark` CSS variable layer. Plotly themes need conditional
   `apply_theme(fig, theme=...)`. ~150 credits.
2. **`system` mode** — react to `prefers-color-scheme` via a small JS
   shim injected by `inject_css`. ~50 credits.
3. **Accent colors** — refactor `COLORS["gold"]` to read from prefs, then
   plumb the picked accent into the chart palette and CSS. The series
   palette stays fixed for chart readability, only the brand accent moves.
   ~80 credits.
4. **Density** — comfortable/compact maps to `padding` + `font-size` CSS
   variables; mostly mechanical. ~70 credits.

**Credit estimate.** ~350 credits for full polish.

**Recommendation.** Defer light theme until there is demonstrated demand
— Protocōl reads better in dark on a desktop, and most users will not toggle.
Ship **accent color** and **density** in a small follow-up pass (~150
credits) since the prefs are already captured and the change is mechanical.
Tag the stubbed-out options as `(v2.1 — not yet active)` in the meantime.

### 6C — iOS / Android conversion path

Three viable paths, evaluated by effort + UX fidelity + maintenance burden:

#### Option A — PWA (Progressive Web App)

- **Effort:** ~200 credits to add a `manifest.json`, service worker, install
  prompt, offline caching for the static shell. Streamlit's web-app nature
  is already PWA-compatible.
- **UX trade-offs:** Push notifications work on Android, are limited on iOS
  Safari. No home-screen integration with HealthKit. Touch targets on
  current layout need a pass — many KPI rows assume desktop widths.
- **Maintenance:** Low. Same codebase.

#### Option B — Native webview wrapper (Capacitor / Tauri / React Native WebView)

- **Effort:** ~500–700 credits. Capacitor wraps the Streamlit URL in a
  native shell, adds a splash screen, push-notification bridges, and a
  HealthKit / Health Connect plugin. Two app store submissions
  (Apple ~$99/year + Google ~$25 one-time).
- **UX trade-offs:** Looks native on the homescreen, but the inner UI is
  still Streamlit. Slow first paint compared to native. HealthKit live
  data can flow through Capacitor plugins.
- **Maintenance:** Moderate — app-store review cycles + plugin upkeep.

#### Option C — Full native rebuild (SwiftUI / Jetpack Compose, OR a React Native frontend)

- **Effort:** ~3,000–5,000 credits per platform. Means walking away from
  Streamlit entirely on mobile — port every page, every chart, every
  preferences flow. The data layer (CSV/JSON in `data/<user>/`) would need
  a JSON API service.
- **UX trade-offs:** Native everything. HealthKit / Health Connect work
  first-class. Push, widgets, watchface complications all possible.
- **Maintenance:** High — three codebases (Streamlit web, iOS, Android).

**Recommendation.** **PWA first** as the v2.1 mobile story. It is the
lowest-cost path that gives Ryan a real home-screen icon, captures
"add to home screen" usage signal, and exposes layout breakpoints that
need fixing. If mobile usage exceeds desktop usage in the next quarter,
revisit **Option B (Capacitor)** for HealthKit integration. **Defer
Option C** unless Protocōl pivots toward a multi-user product — for a
single-user tool, the maintenance cost is irrational.

---

## Task Group 7 — Deferred (do NOT execute without explicit approval)

Each item below was identified as likely to exceed the ~1,000-credit per-item
ceiling. They are documented here for a future planning pass; **none are
executed in this PR.**

### 7.1 — Full notifications system (email + SMS + trigger engine)

- **What it is.** End-to-end alert pipeline: rules → events → debouncer →
  channel adapters (in-app, email, SMS) → digest engine.
- **Why deferred.** Spans backend (trigger engine, debouncer state) + integrations
  (SendGrid/SES, Twilio) + frontend (in-app inbox view, quiet-hours UI). Each
  channel has its own deliverability + compliance surface (CAN-SPAM, TCPA for SMS,
  per-region consent).
- **Credit estimate.** ~1,200–1,500 credits.
- **Value.** High once Protocōl moves beyond a single user; medium for
  Ryan-only — daily review of Home does most of the work today.
- **Recommendation.** Pre-requisite: define the **3–5 alert types** that
  actually warrant interrupting Ryan (e.g. ApoB jump > X, sustained HRV
  drop > Y, missed protocol day count). Build *just those* first as an
  in-app feed (Home Row 2 already exists). Defer email/SMS until in-app
  proves the signal value.

### 7.2 — Full PWA / mobile optimization

- **What it is.** Manifest, service worker, offline cache, touch-target audit,
  responsive breakpoints across every page, HealthKit/Health Connect
  integration via Capacitor.
- **Why deferred.** Layout audit alone is ~400 credits; Capacitor + HealthKit
  plugin is another ~500–700; app-store submission overhead.
- **Credit estimate.** ~1,500–2,000 credits for the full path; ~200 credits
  for a *PWA-only* sub-slice (manifest + service worker + install prompt).
- **Value.** Medium — Ryan primarily uses desktop today, but a mobile
  home-screen view would meaningfully change daily-tracker logging
  friction.
- **Recommendation.** Ship the **PWA sub-slice (~200 credits)** in v2.1 as
  a separate small PR. Defer Capacitor + HealthKit until PWA usage signals
  demand.

### 7.3 — Full LLM intelligence expansion across many pages

- **What it is.** LLM-augmented insights on Bloodwork (per-biomarker
  context), Wearables (recovery narrative), CGM (post-meal analysis),
  Training (load coaching), Risks (interpretive expansion of each flag),
  Recommendations (already partially in place), N=1 (hypothesis generation),
  Timeline (event summarization).
- **Why deferred.** Each page is its own prompt-engineering surface, with
  its own evaluation harness needed to ensure the model doesn't hallucinate
  biomarker values or invent medications. Without an eval harness, every
  expansion is a regression risk.
- **Credit estimate.** ~1,500–2,500 credits for the full sweep + eval harness.
- **Value.** Conditional — high if the model output is reliably tight; low
  to negative if it drifts. Hallucinated biomarker context on Bloodwork is
  a serious trust risk.
- **Recommendation.** Stage in phases:
  1. **Phase 1 (~300 credits).** Eval harness — snapshot a deterministic
     fact-pack from current data, run a fixed prompt set against multiple
     model versions, score for (a) numeric fidelity, (b) absence of
     hallucinated medications/biomarkers, (c) clinical-tone score.
  2. **Phase 2 (~400 credits).** Light expansion: Wearables narrative,
     Bloodwork drill-down context. These are lowest-risk because the
     deterministic chart is right next to the narrative.
  3. **Phase 3 (deferred further).** Risks & Recommendations expansion —
     highest stakes, defer until Phase 1 + 2 are stable.
- **What we did instead in this PR.** Discriminated LLM error states + status
  badge so every LLM-touching page can surface what's actually happening
  (live / key missing / billing / quota / error) without misleading the user.

---

## Security note (from this PR's audit)

- ✅ `.streamlit/secrets.toml` is in `.gitignore` and was never committed.
- ✅ `git log -p -S sk-` and `git log -p -S OPENAI_API_KEY` across all
  branches showed **no committed API keys**, real or otherwise. No rotation
  required.
- The `secrets.toml.example` file in the repo is the placeholder template;
  the real `secrets.toml` is untracked.

---

## Stylistic conventions adopted in this PR

These are recorded so future contributors stay consistent:

- **Chart palette** — `["#4FC3F7", "#FFD54F", "#A5D6A7", "#EF9A9A",
  "#CE93D8", "#80DEEA", "#FFAB91", "#F48FB1"]`. Multi-series charts iterate
  through this list in order.
- **Rolling means** — 7-day window for daily metrics, 3-month window for
  monthly bars. Raw daily values render as faint background (opacity 0.3)
  beneath the rolling line.
- **Time range selectors** — every chart-heavy page persists its choice
  via `modules/time_range.py` keyed on a per-page `page_id`. Presets:
  7d, 30d, 90d, 6mo, 1yr, all, custom.
- **Sources expanders** — placed above the first KPI row on data-heavy
  pages, collapsed by default.
- **PDF export** — `fpdf2` rendered with light markdown-aware formatting
  (headings detected, bullets normalized).
- **`full_height()` for tables** — every `st.dataframe` should pass
  `height=full_height(len(df))` so the table is fully visible (no scroll
  bar inside the table).
- **TODAY anchor** — `pd.Timestamp("2026-05-25")` for demo-time
  computations. The time-range selector respects this on date-bounded queries.

---

*Generated as part of the `feat/protocl-v2-revisions` branch — see the PR for
the full implementation diff.*


---

## v2.0 remediation (feat/protocl-v2-remediation)

Focused follow-up to PR #2 (squash 4022b9f) closing the seven ⚠️ partial items
called out in `protocl_v2_audit.md`. Scope was intentionally narrow — label/
content drift from spec + missing coverage inside already-implemented
features. No new dependencies; no behavioral changes outside the seven
audited items.

### Fix list

1. **Risks & Alerts tile labels + canonical taxonomy** — replaced 6 KPI
   tiles with the spec's 4 (`🔴 Out of Range / 🟡 Suboptimal / 🟢 Optimal /
   ℹ️ Informational`) rendered with emoji + count, all four shown even when
   N=0. Flag grouping now uses a stable canonical taxonomy independent of
   source CSV `panel` strings.
2. **LLM badge on Settings + Integrations** — `llm_badge()` added to both
   page headers.
3. **Data export "All data" + per-CSV downloads** — added "📦 All data"
   sentinel to the multiselect (auto-selects every category) and a row of
   per-category download buttons below the ZIP button.
4. **Clinician summary — three missing sections + split recovery** — added
   Medications, Risks & Alerts, and Patient Notes sections; split the
   merged "Recovery & Cardio Dose" into spec's "Vital Signs & Wearables"
   and "Training & Performance".
5. **Sources Informing Design expanders** — added to the bottom of
   `09_training_activity.py`, `10_zone2_vo2max.py`, and `11_protocol.py`
   with real, page-specific citations.
6. **Persona definitions as a table** — `st.table` with `Persona | Focus`
   columns in `18_settings.py`.
7. **Privacy disclaimer — AI/LLM + experimental-science callouts** — added
   two short sections to `reference/disclaimer.md` covering hallucination
   risk and the research-grade status of PhenoAge / Z2 / optimal ranges /
   TRT / peptides.

### Risks & Alerts — canonical category mapping

This mapping is the authoritative panel-or-biomarker → spec category lookup
used by `protocl/pages/14_risks_alerts.py`. It is intentionally lookup-based
rather than CSV-driven so the page does not silently drift if a lab vendor
relabels a panel.

**Panel → category**

| Source panel       | Canonical category |
|--------------------|--------------------|
| `lipids`           | Cardiovascular     |
| `cardiovascular`   | Cardiovascular     |
| `glucose_insulin`  | Metabolic          |
| `hormones`         | Hormonal           |
| `thyroid`          | Hormonal           |
| `inflammation`     | Inflammatory       |
| `liver`            | Other              |
| `kidney`           | Other              |
| `hematology`       | Other              |
| `vitamins_minerals`| Other              |

**Specific biomarker overrides** (applied first; covers any case where the
panel mapping would land on `Other` but the biomarker has a clearer home):

- **Cardiovascular** — `ldl_c_mg_dl`, `hdl_c_mg_dl`, `apob_mg_dl`,
  `lp_a_nmol_l`, `triglycerides_mg_dl`, `total_cholesterol_mg_dl`
- **Metabolic** — `glucose_mg_dl`, `hba1c_pct`, `fasting_insulin_uiu_ml`,
  `homa_ir`
- **Hormonal** — `testosterone_total_ng_dl`, `testosterone_free_pg_ml`,
  `estradiol_pg_ml`, `cortisol_ug_dl`, `tsh_uiu_ml`, `free_t3_pg_ml`,
  `free_t4_ng_dl`, `dhea_s_ug_dl`, `shbg_nmol_l`, `progesterone_ng_ml`
- **Inflammatory** — `hscrp_mg_l`, `il_6_pg_ml`, `ferritin_ng_ml`
- **Performance** — `vo2max_ml_kg_min`, `hrv_sdnn_ms`, `resting_hr_bpm`

Anything not matched above falls to **Other**. Performance category will
generally only see flags once VO₂max and HRV start showing up in the
bloodwork table; until then it stays empty by design.

---

## Function Health PDF Import

### Why a PDF importer at all
Function Health offers **no public API**. The only supported export of a
member's biomarker data is the *Lab result of record* PDF, downloadable
from `my.functionhealth.com/documents`. Empirical Health and several other
consumer-health apps already ingest the same PDF, confirming the layout
is reliably parseable.

### Parser approach — `protocl/modules/function_health_pdf.py`
Two-stage extraction, both feeding the same row-normalizer:

1. **Table-first** via `pdfplumber.Page.extract_tables()`. We detect column
   semantics from the header row (`biomarker | result | unit | reference
   range | flag`); if the header isn't recognized we fall back to
   positional `(name, value, unit, range)` for the first four columns.
2. **Text fallback** — `pdfplumber.Page.extract_text()` is split into
   lines and matched against a regex:
   `<name> <value> <unit>? <range>?`. The range supports `X - Y`, `< X`,
   and `> X`.

Collection date is harvested from the first two pages by matching
`Collected:`, `Collection Date:`, or `Date:` patterns; if absent we fall
back to the PDF's `CreationDate` metadata field.

### Canonical name map
The page reuses `modules.biomarker_aliases.canonicalize()` first, then
overlays `FUNCTION_EXTRA_ALIASES` in the parser module for Function-specific
phrasings (`"Apo B"`, `"Hemoglobin A1c"`, `"25-OH Vitamin D"`, etc.).
Unrecognized names are kept verbatim, flagged as `unrecognized_name` in
the bloodwork `notes` column, and logged so they can be folded into the
alias table later.

### Page placement — separate file vs. tab
Added as a **new page** (`pages/19b_function_health_import.py`) rather
than folded into `19_integrations.py`. Reasoning:
- The integrations page is a status/dashboard view; a multi-step upload +
  preview + import flow doesn't fit cleanly as a card.
- Function-specific UI elements (PDF uploader, recognized/unrecognized
  counts, post-import diff) keep the integrations page lean.
- Future Function-specific features (auto-classify by panel,
  optimal-range comparison vs. Function's own bands) have an obvious
  home.
A small "Open Function Health Import" entry should be added to the
integrations page later if Function reaches "connected/file-based" status.

### Flag logic
- `value > reference_high` → `High`
- `value < reference_low`  → `Low`
- otherwise                → `Optimal`

Function's PDFs reportedly include an "optimal" band tighter than the
lab reference range. The current parser only models the wider
`reference_low / reference_high` pair; a follow-up should detect the
optimal band column and emit `Suboptimal` for in-range-but-outside-
optimal results.

### Dedupe rule on import
Composite key = `(biomarker_canonical, collection_date)`. If a row with
the same canonical key and date already exists, the new row is skipped.
Rows whose name isn't in the alias table fall back to the raw biomarker
string for the dedupe key, so re-uploading the same PDF still de-dupes
correctly even before alias additions.

### Audit log
A row is appended to `data/<user>/import_log.csv` with
`source_type=function_health_pdf`, matching the schema written by
`migrate_real_data.py` and the manual-entry path in `data_loader.py`.

### To revisit when a real Function PDF arrives
1. Confirm the column order assumed in `_rows_from_table` (currently we
   detect by header keywords; positional fallback may be wrong).
2. Detect and surface the "optimal" band — add `optimal_low` /
   `optimal_high` to the parser output and wire a `Suboptimal` flag.
3. Extend `FUNCTION_EXTRA_ALIASES` with any names that show up as
   `unrecognized` in the real export.
4. Confirm the collection-date regex matches the real PDF's wording (the
   Function PDF may say e.g. *"Specimen collected on Jan 15, 2026"* —
   `_normalize_date` already supports the long-form variants).
5. Decide whether Function-specific "optimal" ranges should override
   Protocōl's own `reference_ranges.csv` for the same biomarkers, or be
   stored alongside as a parallel column.

---

# v3.0 + v3.1 — Sleep + Alerts (branch `feat/protocl-v3-sleep-alerts`)

Decisions made during the combined v3.0 Sleep + v3.1 Alerts implementation.

## Sleep score formula (A1)

**Chosen weights:** Duration 40% · Depth/Quality 30% · HRV 20% · Consistency 10%.

**Rationale.** Sleep duration is the single most evidence-backed lever
(AASM, CDC, Walker), so it gets the largest weight. Depth/REM are
critical for recovery and memory consolidation but data quality from
HealthKit is uneven; we down-weight to 30% to avoid penalizing nights
where stage detection is noisy. HRV is a strong autonomic recovery
signal but moves with many confounders (alcohol, illness, late meals)
so 20% reflects "informative but not authoritative." Consistency
matters chronically more than daily, hence the smaller 10% — it nudges
behavior without dominating any single night's score.

**Verdict thresholds:** ready ≥80 · moderate 60–79 · low <60. Aligned to
Bevel/Whoop-style coaching language so the user reads the verdict before
the number.

## Sleep need adjustments (A2)

**Adjustment magnitudes.**
- Training strain (high)        +45 min
- Training strain (moderate)    +30 min
- HRV 7d down >5% vs 28d        +30 min
- Illness/inflammation          +60 min
- Travel detected               +30 min
- Carryover sleep debt          +45 min

All adjustments are additive on top of an 8h (480 min) base. Caps not
enforced — if a user genuinely has six concurrent stressors, the recommendation
to sleep extra is the correct one. The UI surfaces each adjustment with its
reason so the user can sanity-check.

## Email format (B5)

**Markdown → HTML** rather than a templating engine. Reasons:
1. Zero new dependencies if `markdown` is available; fpdf2-style fallback
   otherwise.
2. The digest is information-dense, not visually demanding — clean tables
   and bullets read fine without custom styling.
3. Easy for the user to copy chunks into a journal or notes app.
4. Templating engines add complexity that pays off only when you have
   marketing-style assets. We don't.

## DST handling for the weekly cron (B5)

Cron expression: `0 1 * * 1` (Sunday 01:00 UTC). This is:
- Sunday **18:00 MST** (winter, UTC-7) — desired
- Sunday **19:00 MDT** (summer, UTC-6) — fires one hour late

Acceptable tradeoff vs. running two crons gated by month-of-year. Ryan
gets a small calendar reminder before each DST transition to confirm
nothing drifted; if the +1hr shift is annoying we'll switch to a
two-cron setup later. `scripts/schedule_weekly_digest.py` documents
both options.

## "First digest is a draft" safety mechanism (B5)

The inaugural weekly digest is created as a Gmail draft via
`create_draft()` rather than sent through SMTP. The gate lives in
`data/<user>/notifications_state.json` under `first_digest_sent: bool`.
After Ryan reviews the draft and is happy, he flips the gate with
`mark_first_digest_reviewed()` (one-shot from a Python REPL) and all
subsequent Sunday digests send live. This prevents a misconfigured
template, a wrong recipient, or a runaway alert evaluator from blasting
out a bad email before Ryan has a chance to see it.

## Hypnogram drilldown placement (A4)

**Decision: same page as the dashboard, inside an expander** rather than
a separate `pages/20a_sleep_night.py`.

Reasons: (a) HealthKit reports per-night stage durations rather than
minute-level, so the drilldown can't show much more than the dashboard
already does; (b) keeping it in an expander avoids nav clutter and the
need to remember a separate URL; (c) the expander pattern matches
how N=1 experiments and protocol entries already work.

If we eventually ingest minute-level Apple Watch sleep events
(third-party tools like AutoSleep can export them) we'll upgrade the
expander into a tab or a dedicated sub-page.

## Single-user mode (cross-cutting)

Confirmed: v3.0 + v3.1 do NOT parameterize by user_id beyond what
already exists in `data_loader.py` (which keys directories by user but
hard-codes `DEFAULT_USER = "ryan"`). Multi-user/family scoping is
explicitly v3.2 and the alerts state files (`alerts_state.json`,
`notifications_state.json`) live inside `data/ryan/` to match.

## Cron registration not auto-fired

`scripts/schedule_weekly_digest.py` is committed for reproducibility but
the cron itself is NOT registered from inside the autonomous build.
Ryan registers it manually after PR review. Reason: a misconfigured
schedule would silently fire incorrect digests until killed; a one-line
manual step is cheap insurance.

## Deferred from this release

- **Jet Lag Protocol Generator** — explicitly out of scope per spec
  cross-cutting constraints. Calendar travel detection in
  `evaluate_travel_detected()` is wired but doesn't yet generate the
  jet-lag plan.
- **LLM recommendation engine** — v3.3. Weekly digest §Recommendations
  surfaces deterministic alerts-derived items rather than calling out
  to an LLM.
- **Multi-user / family scoping** — v3.2.
- **Real Apple HealthKit minute-level event ingest** — depends on
  upstream tooling. v3.0 reads stage durations from `wearables.csv`
  and renders an approximate cyclic pattern for the hypnogram.
- **Live Google Calendar connector** — `evaluate_travel_detected` and
  the wind-down plan A5 currently fall back to default wake time. The
  calendar adapter is a v3.2 prerequisite.


---

## v3.4 — Adaptive UI (Minimal)

### Visibility-state policy

Every section resolves to one of three states via
`data_presence.visibility_state(source_key)`:

- **active** — `has_data(for_trend=True)`: at least `min_rows_for_trend`
  rows (default 3). The section renders as it always has.
- **stub** — `has_data()` but not for a trend: 1–2 rows. The section still
  renders, but charts get an inline "add N more reading(s)" nudge so a
  single point isn't mistaken for a trend.
- **hidden** — no rows. The section is replaced by a single `render_locked_card`
  CTA (or, for a whole page like Bloodwork, the card + `st.stop()`), so beta
  users never see empty tables or flat charts.

**Why a registry instead of inline `df.empty` checks.** Presence rules
(row thresholds, freshness windows, which file backs which source) were
already scattered across pages. Centralizing them in one `DataSource` catalog
means the policy is testable in isolation and the 22 not-yet-migrated pages
have a single contract to adopt.

**Coverage weighting.** `data_coverage_pct()` counts only *primary* sources
(`weight > 0`); the view sources `strava` / `function_health` / `sleep` are
weight 0 because they share a file with a primary source — importing one
bloodwork PDF must not be counted three times. Weights: bloodwork=3;
wearables/training/inbody=2; cgm/ketones/protocol/daily_log=1.

### Snooze / nudge cadence

- **Locked-card dismissal** is per-source and lasts **30 days**
  (`dismissed_nudges.json`). A dismissed card renders nothing; the caller
  decides any fallback.
- **Setup hero** snoozes for **14 days** (`setup_hero_state.json`) but
  *resurfaces early* when the user crosses a **25%** or **50%** coverage
  milestone, so progress feels rewarding rather than nagging. At **≥ 50%**
  coverage the hero never renders again. The decision is a pure function
  (`setup_hero.hero_decision`) so the full lifecycle is unit-tested without
  Streamlit.

### "Show all sections" default

The toggle persists to `appearance.show_empty_sections` in
`user_preferences.json`. Default is **off** for beta users (curated, empty
sections hidden) and **on** for the owner (full layout with empty-state
messaging). Rationale: the owner authors and QAs against every section; beta
friends get the tight, intentional first-run experience. Preferences remain
single-tenant in this codebase (v3.2 isolation applies to the CSV data layer,
not `user_preferences.json`), so the toggle is read the same way every other
page reads prefs.

### Reference-implementation scope

Only **Home** and **Bloodwork** adopt the components in this PR — deliberate,
so we validate the pattern on two real pages before a 22-page sweep. No other
page, the nav structure, or the v3.2 auth/storage flow is touched. **No LLM
calls** are made anywhere in v3.4.
