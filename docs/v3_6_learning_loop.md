# v3.6 — Learning Loop

Instrumentation + feedback machinery to maximize what we learn from the beta:
event tracking, a structured feedback widget, a 7-day NPS micro-survey, a
drop-off detector, and an owner analytics dashboard. **No LLM calls anywhere**;
all per-user persistence flows through `ProfileStorage` so v3.2 isolation holds.

## Event tracking (`modules/events.py`)

`track(event_name, *, page="", **properties)` appends a structured row to the
**current profile's** `events.csv` (`timestamp, event_name, page,
properties_json`) and bumps an **anonymized** daily roll-up.

**Privacy gates**
- Per-user event detail lives ONLY in `data/profiles/<id>/events.csv`.
- The shared roll-up `data/shared/event_rollup_daily.csv` carries
  `date, event_name, count` and **never a `profile_id`** — it is the only event
  data ever written outside a profile dir.
- Tracking is **opt-in**: a user who turned analytics consent off records
  *nothing* — not even the anonymized roll-up.
- The owner may read another user's per-event detail only when that user granted
  v3.2 owner-visibility. Aggregate views use the roll-up, which is identity-free.

**Auto-instrumented in the shell** (no per-page edits): `page_view` on every
render; `session_start` / `session_end` derived from a 30-minute inactivity
window. `session_start` is opened in `shell.boot()` **before** the NPS check so
the survey can fire on the user's literal 7th distinct session.

**Manual instrumentation** in existing components: explainer
(`explainer_expanded`, `explainer_question_asked`), locked section
(`locked_card_shown/clicked/dismissed`), add-data modal
(`modal_opened/completed/abandoned`), setup hero
(`setup_hero_shown/dismissed/cta_clicked`), feedback (`feedback_submitted`),
plus PDF export / CSV import / account actions.

### Event taxonomy (quick reference)

| event | when | key properties |
|-------|------|----------------|
| `page_view` | every render | `page` |
| `session_start` / `session_end` | 30-min window | `duration_min` |
| `explainer_expanded` | explainer opened | `chart_id`, `tier` |
| `locked_card_shown/clicked/dismissed` | v3.4 locked section | `source_key` |
| `modal_opened/completed/abandoned` | v3.4 add-data modal | `source_key`, `records_added` |
| `setup_hero_shown/dismissed/cta_clicked` | v3.4 hero | — |
| `feedback_submitted` | feedback widget | `page`, `sentiment` |
| `nps_submitted` / `nps_dismissed` | NPS modal | `score` |
| `export_pdf` | PDF export | `report_type` |

## Structured feedback (`modules/feedback_v2.py`)

Replaces the free-text-only widget with three questions — **sentiment**
(👍 / 🤔 / 👎, required) plus two optional free-text prompts ("what did you
expect to see here?" and "one thing that would make this better?"). Auto-captures
`page_id, profile_id (private), timestamp, browser user agent, last 5 events`.
The old free-text box is preserved as an **"Or tell us more →"** expander.
Writes to both `data/profiles/<id>/feedback.csv` and the shared
`all_feedback.csv`. `pages/31_admin_feedback.py` adds a sentiment-by-week bar
chart and a **TF-IDF top-complaints cluster** (pure Python, no LLM).

## NPS micro-survey (`modules/nps.py`, `pages/35_admin_nps.py`)

A one-tap 0–10 modal auto-triggers at the user's **7th** distinct
`session_start`, then re-surveys at the **30th** and **60th** (separate rows,
never overwritten). Submit *or* dismiss suppresses the modal until the next
milestone. Responses go to `data/shared/nps_responses.csv`
(`timestamp, profile_id, score, reason, days_active_at_response`).

**Interpreting NPS:** standard buckets — detractor 0–6, passive 7–8, promoter
9–10. Aggregate `NPS = %promoters − %detractors` over each user's latest
response. With a 5-friend beta the absolute number is noisy; watch the
*direction* and read the reasons.

## Drop-off detector (`modules/dropoff.py`, `scripts/dropoff_detector.py`)

Days-inactive is the time since a user's last **`login`** row in the shared
`audit_log.csv` (so users who opted out of analytics are still detected; falls
back to last event when no login row exists). Stages fire once per inactivity
spell and reset when the user returns:

- **7 days** → in-app re-engagement nudge stored on the user's prefs.
- **14 days** → owner notification (in-app + best-effort email).
- **30 days** → auto-pause the user's auto-sync to stop spending credits.

The owner is never nudged or paused. The cron is **registered manually** via
`scripts/register_dropoff_cron.py` (never auto-executed).

## Owner analytics (`pages/36_admin_analytics.py`)

Owner-only, four tabs: **Engagement** (DAU/WAU, top pages, feature-adoption
funnel — from the anonymized roll-up), **Funnel health** (per-user signup →
consent → first-data → 3rd-visit), **Feedback pulse** (sentiment + complaint
cluster + NPS trend), and **Drop-off watchlist** (users at 4+/7+/14+ days
inactive with a one-click "Send check-in"). Engagement uses only the anonymized
roll-up; per-user tabs read state read-only via `ProfileStorage`.

## Privacy consent

The v3.2 consent screen gains a third checkbox — **"Allow anonymized usage
analytics to help improve Protocōl"** — default checked, revocable anytime in
*Settings → Privacy*. When off, `events.track` / `maybe_start_session` record
nothing.
