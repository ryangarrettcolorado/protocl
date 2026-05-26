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
