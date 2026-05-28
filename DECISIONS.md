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
