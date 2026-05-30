# v3.5 — Pre-Share Blockers

The four pieces that had to ship before the 5-friend beta: self-serve account
deletion, per-user automated sync, an in-app changelog, and lightweight error
monitoring. All work preserves the v3.2 per-profile isolation guarantees
(`ProfileStorage`) and makes **no LLM calls**.

## Account deletion (`modules/account_deletion.py`, `pages/95_settings_privacy.py`)

Self-serve, two-step (type your email, then confirm the red **Permanently
delete** button). The orchestrated flow is `delete_account()`:

1. **Audit** `account_delete_initiated`.
2. **Scrub PII** in shared logs — for every shared log that may carry a
   `profile_id` (`all_feedback`, `audit_log`, `llm_cost_log`, `sync_log`,
   `sync_errors`, `nps_responses`, `error_log`) the matching rows have their
   `profile_id` replaced with `deleted_<hash8>` and `display_name` blanked.
   **Rows are never deleted** — the timestamp + action stay for the security
   audit trail.
3. **Soft-delete** the live profile directory into
   `data/deleted/<profile_id>_<timestamp>.zip` (90-day retention for accidental
   deletion), then remove the live directory.
4. **Audit** `account_delete_confirmed` *after* the scrub, so that one
   confirmation row is the single remaining entry that names the deleted profile
   (proof the deletion happened).
5. **Notify** the owner (in-app inbox + best-effort email).

`can_delete()` returns `False` for the owner profile (`ryan`); the page disables
the button with helper text and `delete_account()` raises if called for the
owner — the owner must be removed manually by the developer (deleting it would
brick the app).

**Admin restore** (owner-only, on `pages/30_admin_beta_overview.py`):
`list_soft_deleted()` lists the archives in `data/deleted/`;
`restore_from_soft_delete()` extracts a zip back into `data/profiles/<id>/` and
audits `account_restore_from_soft_delete`.

## Per-user automated sync (`modules/sync_orchestrator.py`)

`run_daily_sync_for_all_profiles()` fans the daily sync out across the allowlist
instead of only the owner:

- **Opt-in per source** lives in `preferences.json` under `auto_sync`
  (`strava`, `apple_health`), default **off**, toggled in *Settings →
  Connections*.
- **Per-source error isolation** — each `(profile, source)` runs in its own
  `try/except`; one user's failure never blocks another's.
- **Cost cap** — at most `DAILY_RUN_CAP = 50` runs per invocation; once hit,
  remaining runs are logged as `skipped` ("sync budget reached") and the owner
  is notified.
- **Logging** — every run appends to `data/shared/sync_log.csv`
  (`timestamp, profile_id, source, status, records_added, error_message`);
  failures also append to `data/shared/sync_errors.csv`.
- **No new sources** — only the existing Strava + Apple Health flows are
  wrapped. The actual per-source work is injected via the `runner` hook so the
  orchestration (iteration, opt-in, isolation, cap, logging) is unit-testable
  and the existing owner scripts remain the real implementation.

`scripts/daily_sync.py` calls `run_orchestrated_sync()` after the owner's own
Strava refresh, guarded so a fan-out failure never breaks the owner's sync.
Owner sync health (last-sync timestamp + recent error count) is surfaced on
`pages/30_admin_beta_overview.py`.

## In-app changelog (`modules/changelog.py`, `pages/96_whats_new.py`)

Parses `CHANGELOG.md` at the repo root into versions/sections. `pages/96` renders
it; visiting the page writes the latest version into
`preferences.json:last_seen_changelog_version`. The top-nav shows a red "What's
new" dot while there's an unseen version, and the Home page shows a dismissible
banner once per version.

## Error monitoring (`modules/error_capture.py`, `pages/34_admin_errors.py`)

`capture_error(exc, page, profile_id)` writes a structured row to
`data/shared/error_log.csv`
(`timestamp, profile_id, page, exception_type, message, traceback_hash,
user_facing_message`). Identical errors are **deduplicated by `traceback_hash`**:
a new row is only written when the hash changes or more than an hour has passed
since the last identical error. Page execution in `app.py` is wrapped in a
`try/except` that captures the error and renders a friendly "Something went
wrong" page with a **Send context to Ryan** button (files a feedback entry with
the error context). `pages/34_admin_errors.py` (owner-only) lists recent errors,
top errors by frequency, and a "Mark as fixed" toggle.

**Daily error digest** — `scripts/error_digest.py` reads the last 24h of
`error_log.csv`, groups by `traceback_hash`, and notifies the owner (in-app +
email) only when there are errors. The cron is **registered manually** by the
owner via `scripts/register_error_digest_cron.py` (never auto-executed).
