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
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure ``protocl`` is importable when run from repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
)
log = logging.getLogger("daily_sync")


def sync_healthkit() -> int:
    """Pull Health Auto Export JSON files from Drive and ingest. Returns
    0 on success, 1 on error."""
    if not os.environ.get("HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID"):
        log.info("HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID not set — skipping healthkit sync")
        return 0
    if not os.environ.get("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"):
        log.info("GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON not set — skipping healthkit sync")
        return 0

    try:
        from protocl.modules.sync_drive import sync_health_auto_export
    except ImportError as e:
        log.error("Failed to import sync_drive: %s", e)
        return 1

    try:
        report = sync_health_auto_export(data_dir="protocl/data/ryan")
    except Exception as e:
        log.exception("healthkit sync raised: %s", e)
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
    return 0


def main() -> int:
    failures = 0
    log.info("=== daily_sync starting ===")
    failures += sync_healthkit()
    log.info("=== daily_sync done (%d task failures) ===", failures)
    return failures


if __name__ == "__main__":
    sys.exit(main())
