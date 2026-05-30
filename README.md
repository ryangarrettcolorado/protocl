# Protocōl — Personal Health Intelligence OS

A 17-page Streamlit application that turns quarterly bloodwork, body comp scans,
wearables, CGM, training, and protocol data into a single longitudinal view
with biological-age scoring, N=1 experiment tracking, risk detection, and
LLM-augmented recommendations.

Built across 4 sessions from a single master prompt. Demo data anchored to
**May 25, 2026** for a 42-year-old male on TRT + peptides.

---

## Quick start

```bash
unzip protocl_final.zip && cd protocl
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open <http://localhost:8501>. Everything works in demo mode with no secrets.

### Enable the LLM features

Drop a key into `.streamlit/secrets.toml`:

```toml
OPENAI_API_KEY = "sk-..."
```

Pages 13 (Recommendations) and 15 (Clinician Summary) will flip from
**DEMO MODE** to **LLM LIVE**. The rule-based engine still drives the
deterministic output — the LLM only rewrites/expands it.

### Enable GitHub data sync

```toml
GITHUB_TOKEN  = "ghp_..."           # fine-grained PAT with contents:write
GITHUB_REPO   = "owner/repo"        # private repo for snapshots
GITHUB_BRANCH = "main"              # optional
```

A nightly Actions workflow (`.github/workflows/snapshot.yml`) commits every
CSV/JSON under `data/<user>/` to the configured repo. Trigger manually any
time via **Actions → Protocōl — Nightly data snapshot → Run workflow**.

---

## v3.0 + v3.1 features

### 🌙 Sleep (v3.0)

Bevel-quality sleep coaching tuned to Ryan's TRT + peptide + Anavar +
Retatrutide protocol. The new **Sleep** nav group hosts a single page
with:

- **Today's verdict** — transparent 0–100 sleep score with a "see formula"
  expander showing the weighted blend (Duration 40 / Depth-Quality 30 /
  HRV 20 / Consistency 10) and the verdict thresholds.
- **Sleep need calculator** — personalized 8h baseline adjusted by
  training strain, HRV trend, illness signals, travel, and carryover
  debt; the UI explains every adjustment.
- **7-night score trend + sleep-debt accumulator** running 7d cumulative
  deficit vs. need.
- **Stage breakdown** for last night + multi-line stage trends across
  the selected window, HRV / RHR overnight charts with 7d rolling mean +
  28d baseline reference line, consistency scatter.
- **Hypnogram drilldown** in an expander (HealthKit ships per-night stage
  durations; the page renders an approximate cyclic pattern with a
  clearly-labeled caveat).
- **Wind-down plan** with peptide-aware timing (CJC-1295+Ipam 30 min
  before bed empty stomach) and caffeine cutoff derived from a 5.5h
  half-life curve.
- **Smart-alarm window** — 90-min cycle approximation, ±18/12 min wake band.
- **Stress-Sleep correlation view** — Pearson r vs next-day HRV across
  sleep components and subjective journal fields.
- **Protocol overlays** — sleep score on TRT days vs non-TRT days,
  Retatrutide-day cycle, etc.
- **3-tap morning journal** on Home (5am–noon local) — Mood / Fatigue /
  Soreness sliders persisted to `data/<user>/sleep_journal.csv`.

Data sources: `wearables.csv` (Apple Health), `sleep_journal.csv`,
`caffeine_log.csv`. All formulas live in `modules/sleep_score.py`,
`modules/sleep_need.py`, `modules/sleep_data.py`, `modules/caffeine.py`
and are unit-tested.

### 🚨 Alerts (v3.1)

A dedicated alerts engine + dispatcher:

- **Home banner** — "Today's Watchlist" strip at the top of Home with
  the top 5 active alerts grouped by severity (Critical / Warning /
  Info), inline snooze + dismiss.
- **Alerts page** under the 🚨 Alerts nav group — full active list +
  30-day history tab, per-alert evidence view.
- **Evaluator catalog** (`modules/alerts.py`): bloodwork cadence (Q1
  panel, quarterly draw, Anavar mid-cycle ALT/AST, Lp(a) one-shot),
  biomarker thresholds (Hct, ALT, AST, ApoB, hs-CRP, sensitive E2),
  supplement reorder days-remaining, protocol scheduling, data
  freshness, sleep-specific (rolling debt, HRV z-score), calendar-aware.
- **Inventory page** — `data/<user>/supplement_inventory.csv` editor +
  decay logic; "Bootstrap from protocol.csv" pre-populates from the
  active supplement stack.
- **Settings → Alerts** — master toggle per category, per-biomarker
  threshold overrides, digest cadence + day/time, bloodwork cadence
  configuration.
- **Weekly email digest** (`modules/notifications.py`) — Sunday 6pm MT,
  markdown rendered to clean HTML, Gmail SMTP. **Safety gate:** the
  inaugural digest is created as a Gmail draft via `create_draft()`
  rather than sent; flip `first_digest_sent` in
  `data/<user>/notifications_state.json` (or call
  `mark_first_digest_reviewed()`) after reviewing.
- **Urgent alert path** — `send_urgent_alert()` fires same-day for new
  critical alerts, with 12h dedupe.

Cron registration is reproducible from `scripts/schedule_weekly_digest.py`.
Run it from Perplexity Computer manually after reviewing this PR.

---

## Pages

| # | Page | What it does |
|---|---|---|
| 1 | **Overview** | KPI strip, longitudinal trend with protocol overlays, active risks |
| 2 | **Protocol** | Active items, Gantt timeline, change log, effectiveness, add new |
| 3 | **Bloodwork** | Panels grouped by system, drill into any biomarker, optimal ranges |
| 4 | **Body Composition** | InBody scans, lean mass / BF% trend, visceral fat tracking |
| 5 | **CGM Glucose** | 24h overlay, time-in-range, AGP, daily ridgeline |
| 6 | **Training Activity** | Volume, intensity distribution, TSS, weekly load |
| 7 | **Zone 2 / VO₂ max** | Z2 minutes per week, VO₂ max trend, training quality |
| 8 | **Wearables** | Sleep, HRV, RHR, SpO₂, recovery score trends |
| 9 | **Daily Trackers** | Macros, water, sleep quality, ketone + GKI |
| 10 | **Biological Age** | Levine 2018 PhenoAge — trend, biomarker contributions, sensitivity sliders |
| 11 | **N=1 Experiments** | Active/completed tabs, effect-size barchart, design form |
| 12 | **Risks & Alerts** | Out-of-range, adverse trends, drug-interaction rules |
| 13 | **Recommendations** | Rule-based engine + optional LLM weekly briefing |
| 14 | **Action Items** | Kanban + table, complete/dismiss writes back to CSV |
| 15 | **Clinician Summary** | Deterministic markdown handoff + optional LLM physician-voice rewrite |
| 16 | **Timeline** | 47-event unified feed across every data source |
| 17 | **Import Center** | CSV/Excel upload, auto-mapping, validation, dedup, write to `data/` |

---

## Architecture

```
protocl/
├── app.py                       # entry point — splash + navigation hint
├── requirements.txt
├── .streamlit/
│   ├── config.toml              # dark theme + page config
│   └── secrets.toml.example     # template for API keys
├── .github/workflows/
│   └── snapshot.yml             # nightly GitHub data sync
├── pages/                       # 17 multipage routes (01_*.py through 17_*.py)
├── modules/
│   ├── theme.py                 # injected CSS + sidebar brand block
│   ├── charts.py                # apply_theme, sparkline, metric_card_html, status_*
│   ├── data_loader.py           # @st.cache_data wrapper for every CSV/JSON
│   ├── biomarker_aliases.py     # ~120 lab-name aliases → canonical keys
│   ├── reference_ranges.py      # ~50 biomarker optimal-range definitions
│   ├── bioage.py                # Levine 2018 PhenoAge + Gompertz mortality
│   ├── llm.py                   # OpenAI hookup with graceful demo fallback
│   ├── github_sync.py           # GitHub Contents API writer + cron CLI
│   └── ingest/
│       ├── healthkit.py         # Apple Health export.xml parser
│       ├── whoop.py             # OAuth2 scaffold (stubbed _LIVE=False)
│       └── oura.py              # PAT-based scaffold (stubbed _LIVE=False)
├── data/ryan/                   # demo user — 12 CSV/JSON files
│   ├── bloodwork.csv            # 180 rows · 4 quarterly draws
│   ├── protocol.csv             # 13 protocol items (10 active)
│   ├── inbody.csv               # 12 monthly scans
│   ├── training.csv             # ~100 activities
│   ├── wearables.csv            # 90 days of daily summaries
│   ├── cgm_readings.csv         # 5-min Dexcom sample
│   ├── ketone_readings.csv
│   ├── daily_log.csv            # macros + sleep
│   ├── action_items.csv         # 5 open + completed items
│   ├── context_notes.csv        # travel, illness, deload markers
│   ├── nof1_experiments.json    # 3 N=1 trials
│   └── import_log.csv
└── reference/
    └── biomarker_reference.json # ~50 biomarkers w/ lab + optimal ranges
```

### Theme + style

Every page injects the same CSS via `modules.theme.inject_css()` immediately
after `st.set_page_config(...)`. This is required because Streamlit's
multipage routing doesn't cascade CSS across page navigation. The same module
also renders the `Protocōl` sidebar brand block.

### Data layer

`modules/data_loader.py` is the single seam — every page imports `load_data()`
which returns a `HealthData` dataclass with one DataFrame per source. Cached
for 5 minutes via `@st.cache_data`. Mutations (action item status changes,
form submissions, imports) call `append_row(...)` or rewrite the CSV in place
and clear the cache.

In Phase 2, the same writer will also call `modules.github_sync.put_file(...)`
to mirror changes upstream.

### Biological age

`modules/bioage.py` implements Levine 2018 PhenoAge from 9 biomarkers
(albumin, creatinine, glucose, hsCRP, lymphocyte %, MCV, RDW, alkaline
phosphatase, WBC) + chronological age. Unit conversions are baked in
(albumin g/dL→g/L, creatinine mg/dL→µmol/L, glucose mg/dL→mmol/L,
ln(hsCRP)). Returns a `PhenoAgeResult` dataclass with per-biomarker
contribution decomposition so Page 10 can show what's driving the score.

Reference: <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5940111/>

### LLM hookup

`modules/llm.py` wraps a single-shot OpenAI chat call with `@st.cache_data`
(10 min TTL) so reruns don't burn tokens. When no key is configured every
function returns a clear placeholder and the page renders deterministic
rule-based output instead. Pages call:

```python
from modules.llm import llm_chat, is_configured, llm_badge

if is_configured():
    out = llm_chat(prompt, system=..., model="gpt-4o-mini", max_tokens=1200)
```

### Import Center

Page 17 supports CSV / TSV / XLSX upload for all 8 source types:

- Auto-detects column names via case-insensitive + normalized matching
- Wide-format lab CSVs (one biomarker per column) auto-melted to long format
- Lab biomarker names normalized via `modules/biomarker_aliases.py` (e.g.
  `LDL-C`, `ldl-c`, `LDL Cholesterol`, `LDL Direct` all map to `ldl_c_mg_dl`)
- Validates required columns, null values, date parsing
- Dedups against existing data using source-specific keys
- Atomic append + import log entry

Template downloads available for every source on the Templates tab.

### Importing Function Health Results

Function Health doesn't offer a public API, but they provide a *Lab result of
record* PDF that contains all of your tested biomarkers.

1. Sign in to <https://my.functionhealth.com/documents> and download the most
   recent **Lab result of record** PDF.
2. In Protocōl, open **Function Health Import** (page 19b).
3. Drop the PDF onto the uploader. The parser runs **locally inside the
   Streamlit process** — nothing leaves your machine.
4. Review the preview. You'll see total biomarkers parsed, how many were
   matched against the canonical alias table, and the detected collection
   date.
5. Click **Import to Bloodwork**. Rows are appended to `bloodwork.csv` with
   `source_lab = "Function Health"`. Duplicates (same canonical biomarker +
   collection date) are skipped; unrecognized names are imported under their
   raw label and flagged in the `notes` column.

See `DECISIONS.md → Function Health PDF Import` for parser internals,
canonical name map, and the open follow-ups (optimal-range band, additional
aliases) to address once a real PDF is available for validation.

### Live-API scaffolds

`modules/ingest/` ships three scaffolds:

- **healthkit.py** — full Apple Health `export.xml` parser, no API key needed
- **whoop.py** — OAuth2 refresh-token flow, `_LIVE=False` until secrets are set
- **oura.py** — PAT-based, `_LIVE=False` until `OURA_PAT` is set

Each module exposes `is_configured()` + a `pull_*()` function returning rows
in the relevant target schema. The Import Center will gain an "API pull" tab
in a future session to invoke them directly.

---

## Configuration reference

All secrets live in `.streamlit/secrets.toml` or environment variables. A
template is shipped at `.streamlit/secrets.toml.example`.

| Secret | Purpose | Required? |
|---|---|---|
| `OPENAI_API_KEY` | LLM rewriting on Pages 13 + 15 | No (demo fallback) |
| `GITHUB_TOKEN`   | GitHub data sync | No |
| `GITHUB_REPO`    | `owner/repo` for sync target | No |
| `GITHUB_BRANCH`  | Defaults to `main` | No |
| `WHOOP_CLIENT_ID` / `WHOOP_CLIENT_SECRET` / `WHOOP_REFRESH_TOKEN` | Whoop pull | Future |
| `OURA_PAT`       | Oura daily summary pull | Future |

---

## Deploy

The app runs anywhere Python + Streamlit run. Some patterns that work well:

- **Streamlit Community Cloud** — point at the GitHub repo, set secrets in
  the UI, done.
- **Fly.io / Render / Railway** — `streamlit run app.py --server.port $PORT`.
- **Tailscale + a Mac mini at home** — single-user, no public exposure.

Demo data is committed under `data/ryan/`. To deploy with your own data,
replace files in that directory or use the Import Center.

---

## v3.2 Beta Tier + v3.3 AI Explainers

Protocōl is now a private, invite-only **multi-user beta** with per-user data
isolation, and every key chart carries an **AI "Explain this chart"** block.

### v3.2 — Beta Tier (Google SSO multi-user)

- **Google sign-in** via Streamlit's native OIDC (`st.login` / `st.user`).
  Configure the provider under `[auth]` in `.streamlit/secrets.toml` — see
  `.streamlit/secrets.toml.example`.
- **Allowlist** (`config/allowlist.yaml`) caps access at the owner + 5 beta
  users. Anyone signing in with an off-list address gets a denial screen.
- **Per-user data isolation** — `ProfileStorage` resolves every read/write to
  `data/profiles/<profile_id>/`. The owner reuses the legacy `data/ryan/`.
  `profile_id` is read from session state and is **never** a constructor
  argument, so page code physically cannot reach another user's directory.
- **Owner impersonation** (opt-in, read-only) — Ryan can view a beta user's
  dashboard only if they consent under **Settings → Privacy**. A banner is
  shown, all writes are blocked, and the event is audit-logged.
- **Consent + audit + feedback** — timestamped (non-destructive) revocation,
  one-way SHA-256 IP hashing, an in-app feedback widget, and four owner-only
  admin pages (Beta Overview, Feedback, Audit Log, LLM Costs).

See [`docs/v3_2_beta_tier.md`](docs/v3_2_beta_tier.md) for the full design.

### v3.3 — AI Explainers (Top 30 charts)

- **30 chart surfaces** (`explainers/registry.py`) each render an
  **"💡 Explain this chart"** expander.
- **Three tiers** — Tier 1 educational (deterministic + cached), Tier 2
  personalized (per-user cached), Tier 3 free-form Q&A (uncached).
- **14 Tier-1 biomarkers** are interpreted by a **deterministic rules engine**
  (`explainers/rules/`); the LLM only wraps the structured facts in prose and
  never invents clinical claims.
- **Data minimization** — only the specific chart data is sent to the model,
  scrubbed of all PII (name, email, profile id). A runtime guard + the
  `test_data_minimization.py` suite enforce this.
- **Cost control** — `gpt-4o-mini` for Tier 1/2, `gpt-4o` for Tier 3 chat;
  Tier-1 cache TTL 30 days; per-user limits (50 Tier 2/day, 10 Tier 3/day) and
  a 500-call/day per-app ceiling, tracked in the owner LLM Cost dashboard.

See [`docs/v3_3_explainers.md`](docs/v3_3_explainers.md) for the full design.

### Beta setup

```toml
# .streamlit/secrets.toml
[auth]
redirect_uri = "https://<your-app>.streamlit.app/oauth2callback"
cookie_secret = "<random-string>"
client_id = "<google-oauth-client-id>"
client_secret = "<google-oauth-client-secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

OPENAI_API_KEY = "sk-..."   # enables Tier 1/2/3 explainer prose
```

Then edit `config/allowlist.yaml` to add the owner email and up to 5 beta
addresses. Beta users get an empty profile on first login and can opt into
realistic onboarding data (copied from `data/samples/`).

---

## Sessions

Build broken into 4 sessions from one master prompt:

1. **Session 1** — Scaffold, theme, data layer, Pages 1-3 (Overview, Protocol, Bloodwork)
2. **Session 2** — Pages 4-9 (Body Comp, CGM, Training, Z2/VO₂max, Wearables, Daily)
3. **Session 3** — Pages 10-16 (Bio Age, N=1, Risks, Recommendations, Action Items, Clinician Summary, Timeline) + `bioage.py` + `llm.py`
4. **Session 4** — Page 17 (Import Center), GitHub sync, ingest scaffolds, polish, QA, docs

---

## License

Single-user personal project. Not medical advice. Optimization thresholds in
`reference/biomarker_reference.json` are tighter than standard lab reference
ranges — they reflect longevity-medicine targets, not clinical diagnostic
cutoffs. Use as a discussion aid with your clinician.
