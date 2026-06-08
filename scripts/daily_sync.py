"""Scheduled sync entry point for GitHub Actions.

Runs every 6 hours (see ``.github/workflows/sync.yml``). Each sync task
is self-contained — failure in one does not block the others.

Tasks currently wired up:
1. **healthkit_json** — pull new Health Auto Export JSON files from
   Google Drive and merge into ``protocl/data/ryan/`` CSVs.
2. **strava** — placeholder for the existing daily Strava refresh
   (handled separately by an older mechanism that already produces
   ``chore(sync): daily Strava refresh`` commits).

Exit code is the count of tasks that errored. ``0`` is success.

Also writes a status JSON to ``protocl/data/ryan/healthkit_sync_status.json``
so the running Streamlit app can show the truthful pipeline state to the
user — "service account not configured" vs "connected, 0 files" vs
"connected, last sync 3h ago, 124 rows added" — instead of guessing from
file-system mtimes.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure ``protocl`` is importable when run from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
log = logging.getLogger("daily_sync")

STATUS_PATH = REPO_ROOT / "protocl" / "data" / "ryan" / "healthkit_sync_status.json"


def _write_status(
    *,
    state: str,
    detail: str,
    files_seen: int = 0,
    files_processed: int = 0,
    rows_added: int = 0,
    rows_wearables: int = 0,
    rows_cgm: int = 0,
    rows_inbody: int = 0,
    errors: list[str] | None = None,
) -> None:
    """Persist the latest sync result so the app can read & display it.

    ``state`` is one of: ``not_configured``, ``connected_no_data``,
    ``connected_with_data``, ``error``. The app's HealthKit alert reads
    this file and shows a truthful, actionable message based on the state.
    """
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state": state,
        "detail": detail,
        "last_run_utc": datetime.now(tz=timezone.utc).isoformat(),
        "files_seen": files_seen,
        "files_processed": files_processed,
        "rows_added": rows_added,
        "rows_wearables": rows_wearables,
        "rows_cgm": rows_cgm,
        "rows_inbody": rows_inbody,
        "errors": errors or [],
    }
    STATUS_PATH.write_text(json.dumps(payload, indent=2))
    log.info("wrote sync status: state=%s detail=%s", state, detail)


def sync_healthkit() -> int:
    """Pull Health Auto Export JSON files from Drive and ingest. Returns
    0 on success, 1 on error."""
    folder_id = os.environ.get("HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID")
    sa_json = os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")

    # Loud, scannable banner so it's the first thing you see in the
    # workflow log when debugging.
    log.info("────────── healthkit pipeline preflight ──────────")
    log.info("  HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID : %s",
             "SET" if folder_id else "NOT SET (set in GitHub Secrets to enable)")
    log.info("  GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON  : %s",
             "SET" if sa_json else "NOT SET (set in GitHub Secrets to enable)")
    log.info("────────────────────────────────────────────────────")

    if not folder_id or not sa_json:
        missing = []
        if not folder_id:
            missing.append("HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID")
        if not sa_json:
            missing.append("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON")
        _write_status(
            state="not_configured",
            detail=f"Missing GitHub Secrets: {', '.join(missing)}. "
                   "See docs/operator-runbook.md to enable HealthKit sync.",
        )
        log.info("skipping healthkit sync (secrets missing)")
        return 0

    try:
        from protocl.modules.sync_drive import sync_health_auto_export
    except ImportError as e:
        log.error("Failed to import sync_drive: %s", e)
        _write_status(state="error", detail=f"Import error: {e}",
                      errors=[str(e)])
        return 1

    try:
        report = sync_health_auto_export(data_dir="protocl/data/ryan")
    except Exception as e:
        log.exception("healthkit sync raised: %s", e)
        _write_status(state="error", detail=f"Sync raised: {e}",
                      errors=[str(e)])
        return 1

    log.info(
        "healthkit_json: %d files seen, %d processed, %d skipped, "
        "%d rows added (wearables=%d cgm=%d inbody=%d), errors=%d",
        report.files_seen, report.files_processed, report.files_skipped,
        report.rows_added, report.rows_added_wearables,
        report.rows_added_cgm, report.rows_added_inbody,
        len(report.errors),
    )
    if report.errors:
        for err in report.errors:
            log.warning("healthkit_json error: %s", err)
    if report.skipped_metrics:
        log.info("healthkit_json skipped unmapped metrics: %s",
                 ", ".join(report.skipped_metrics))

    if report.rows_added > 0:
        state = "connected_with_data"
        detail = (
            f"Synced {report.files_processed} file"
            f"{'s' if report.files_processed != 1 else ''}, "
            f"{report.rows_added} new row{'s' if report.rows_added != 1 else ''} added."
        )
    elif report.files_seen == 0:
        state = "connected_no_data"
        detail = (
            "Drive folder is empty. Confirm Health Auto Export's automation "
            "is writing JSON files to the shared folder."
        )
    else:
        state = "connected_no_data"
        detail = (
            f"Saw {report.files_seen} file(s) but added 0 rows — likely all "
            "already processed or empty payloads."
        )
    _write_status(
        state=state,
        detail=detail,
        files_seen=report.files_seen,
        files_processed=report.files_processed,
        rows_added=report.rows_added,
        rows_wearables=report.rows_added_wearables,
        rows_cgm=report.rows_added_cgm,
        rows_inbody=report.rows_added_inbody,
        errors=[str(e) for e in report.errors],
    )
    return 0


def main() -> int:
    failures = 0
    log.info("=== daily_sync starting ===")
    failures += sync_healthkit()
    log.info("=== daily_sync done (%d task failures) ===", failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
