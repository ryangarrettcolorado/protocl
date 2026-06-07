"""Google Drive → Protocōl sync watcher for Health Auto Export files.

This module is the bridge between the iOS Health Auto Export app and the
Protocōl data pipeline. The app drops timestamped JSON files into a Drive
folder; this watcher reads them, ingests them through
``modules.ingest.healthkit_json.parse_export``, merges into the canonical
CSVs, and archives the source file so we don't re-process it.

Auth
----
Uses a Google service account whose JSON key is stored in the
``GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON`` env var (Streamlit Cloud Secrets or
a GitHub Actions secret). The user shares the source folder with the
service account's email address — same one-time-setup pattern as the
existing GitHub sync.

Configuration
-------------
Two env vars drive the watcher:

* ``HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID`` — folder ID of ``Protocl-HealthAutoExport/``
* ``HEALTH_AUTO_EXPORT_ARCHIVE_FOLDER_ID`` — folder ID for ``_processed/``
  (optional; if omitted, processed files are renamed in-place with a
  ``.processed`` suffix so subsequent runs skip them.)

The folder ID is the long string in the Drive URL when you open the folder:
``https://drive.google.com/drive/folders/<ID>``.

Usage
-----
::

    from modules.sync_drive import sync_health_auto_export
    report = sync_health_auto_export(data_dir="protocl/data/ryan")
    print(f"Synced {report.files_processed} files, "
          f"{report.rows_added} new rows")

Designed to be called from ``scripts/daily_sync.py`` on a schedule. Safe
to run concurrently with the existing Strava sync because each task
writes to disjoint files.
"""
from __future__ import annotations

import io
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from protocl.modules.ingest.healthkit_json import (
    IngestResult,
    merge_into_csv,
    parse_export,
)

logger = logging.getLogger(__name__)


# ─── Configuration ───────────────────────────────────────────────────────

FOLDER_ENV = "HEALTH_AUTO_EXPORT_DRIVE_FOLDER_ID"
ARCHIVE_ENV = "HEALTH_AUTO_EXPORT_ARCHIVE_FOLDER_ID"
SA_ENV = "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"


@dataclass
class SyncReport:
    """Summary of one sync invocation. Logged to import_log.csv."""
    files_seen: int = 0
    files_processed: int = 0
    files_skipped: int = 0
    rows_in: int = 0
    rows_added_wearables: int = 0
    rows_added_cgm: int = 0
    rows_added_inbody: int = 0
    skipped_metrics: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ran_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def rows_added(self) -> int:
        return self.rows_added_wearables + self.rows_added_cgm + self.rows_added_inbody

    def as_log_rows(self) -> list[dict[str, Any]]:
        """Rows to append to ``import_log.csv`` — one per CSV touched."""
        rows = []
        ts = self.ran_at
        if self.rows_added_wearables:
            rows.append({"timestamp": ts, "source_type": "healthkit_json",
                         "filename": f"drive_sync ({self.files_processed} files)",
                         "rows_imported": self.rows_added_wearables,
                         "rows_skipped_duplicate": 0, "errors": "",
                         "imported_by": "sync_drive.healthkit_json:wearables"})
        if self.rows_added_cgm:
            rows.append({"timestamp": ts, "source_type": "healthkit_json",
                         "filename": f"drive_sync ({self.files_processed} files)",
                         "rows_imported": self.rows_added_cgm,
                         "rows_skipped_duplicate": 0, "errors": "",
                         "imported_by": "sync_drive.healthkit_json:cgm"})
        if self.rows_added_inbody:
            rows.append({"timestamp": ts, "source_type": "healthkit_json",
                         "filename": f"drive_sync ({self.files_processed} files)",
                         "rows_imported": self.rows_added_inbody,
                         "rows_skipped_duplicate": 0, "errors": "",
                         "imported_by": "sync_drive.healthkit_json:inbody"})
        return rows


# ─── Google Drive client (lazy import so tests don't need credentials) ────

def _drive_service():
    """Build a Drive v3 service from the SA JSON in env. Returns None when
    credentials aren't configured — the caller can decide what to do."""
    raw = os.environ.get(SA_ENV)
    if not raw:
        logger.warning("%s not set; sync_drive cannot run.", SA_ENV)
        return None

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        logger.error("googleapiclient not installed: %s", e)
        return None

    try:
        info = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("%s is not valid JSON: %s", SA_ENV, e)
        return None

    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _list_pending(service, folder_id: str) -> list[dict]:
    """List JSON files in the folder that haven't been marked processed.

    A file is 'pending' iff (a) it's a JSON file by mimeType OR name, and
    (b) its name does NOT end in ``.processed``.
    """
    q = (f"'{folder_id}' in parents and trashed = false and "
         f"(mimeType = 'application/json' or name contains '.json')")
    items = []
    page_token = None
    while True:
        resp = service.files().list(
            q=q,
            fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
            pageToken=page_token,
            pageSize=100,
        ).execute()
        for f in resp.get("files", []):
            if f.get("name", "").endswith(".processed"):
                continue
            items.append(f)
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    # Process oldest first so we maintain temporal order
    items.sort(key=lambda f: f.get("modifiedTime", ""))
    return items


def _download(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()


def _archive(service, file_id: str, name: str, archive_folder_id: Optional[str]) -> None:
    """Move file to archive folder (preferred) or rename in-place."""
    if archive_folder_id:
        # Move: add archive parent, remove all others
        meta = service.files().get(fileId=file_id, fields="parents").execute()
        prev_parents = ",".join(meta.get("parents", []))
        service.files().update(
            fileId=file_id,
            addParents=archive_folder_id,
            removeParents=prev_parents,
            fields="id, parents",
        ).execute()
    else:
        # Rename: append .processed so the next run skips it
        new_name = name + ".processed"
        service.files().update(
            fileId=file_id, body={"name": new_name}, fields="name",
        ).execute()


# ─── Main entry point ────────────────────────────────────────────────────

def sync_health_auto_export(
    *,
    data_dir: str = "protocl/data/ryan",
    dry_run: bool = False,
) -> SyncReport:
    """Pull all pending Health Auto Export JSON files from Drive, ingest,
    merge into CSVs, archive sources, append to import_log.

    ``dry_run=True`` downloads and parses but does NOT write CSVs or
    archive files — useful for one-shot diagnostics from a Streamlit
    settings page.
    """
    report = SyncReport()

    folder_id = os.environ.get(FOLDER_ENV)
    archive_id = os.environ.get(ARCHIVE_ENV)
    if not folder_id:
        report.errors.append(f"{FOLDER_ENV} not set")
        return report

    service = _drive_service()
    if service is None:
        report.errors.append("Google Drive credentials not configured")
        return report

    try:
        pending = _list_pending(service, folder_id)
    except Exception as e:
        report.errors.append(f"Drive list failed: {e}")
        return report

    report.files_seen = len(pending)

    data_path = Path(data_dir)
    wearables_path = data_path / "wearables.csv"
    cgm_path = data_path / "cgm_readings.csv"
    inbody_path = data_path / "inbody.csv"
    import_log_path = data_path / "import_log.csv"

    combined_wearables = []
    combined_cgm = []
    combined_inbody = []
    skipped_metrics: set[str] = set()

    for f in pending:
        try:
            raw = _download(service, f["id"])
        except Exception as e:
            report.errors.append(f"{f['name']}: download failed: {e}")
            report.files_skipped += 1
            continue

        try:
            result: IngestResult = parse_export(raw)
        except Exception as e:
            report.errors.append(f"{f['name']}: parse failed: {e}")
            report.files_skipped += 1
            continue

        report.rows_in += result.rows_in
        skipped_metrics.update(result.skipped_metrics)
        if not result.wearables.empty:
            combined_wearables.append(result.wearables)
        if not result.cgm_readings.empty:
            combined_cgm.append(result.cgm_readings)
        if not result.inbody.empty:
            combined_inbody.append(result.inbody)

        if not dry_run:
            try:
                _archive(service, f["id"], f["name"], archive_id)
            except Exception as e:
                # Non-fatal: file is parsed, just won't be archived
                report.errors.append(f"{f['name']}: archive failed: {e}")
        report.files_processed += 1

    report.skipped_metrics = sorted(skipped_metrics)

    if dry_run:
        return report

    # ── Merge into canonical CSVs ────────────────────────────────────
    if combined_wearables:
        new = pd.concat(combined_wearables, ignore_index=True, sort=False)
        # Last-write-wins per (date) when multiple files cover the same day
        new = new.drop_duplicates(subset=["date"], keep="last")
        merged, added, _ = merge_into_csv(new, str(wearables_path), key_cols=["date"])
        if not merged.empty:
            merged.to_csv(wearables_path, index=False)
        report.rows_added_wearables = added

    if combined_cgm:
        new = pd.concat(combined_cgm, ignore_index=True, sort=False)
        new = new.drop_duplicates(subset=["datetime"], keep="last")
        merged, added, _ = merge_into_csv(new, str(cgm_path), key_cols=["datetime"])
        if not merged.empty:
            merged.to_csv(cgm_path, index=False)
        report.rows_added_cgm = added

    if combined_inbody:
        new = pd.concat(combined_inbody, ignore_index=True, sort=False)
        new = new.drop_duplicates(subset=["date"], keep="last")
        merged, added, _ = merge_into_csv(new, str(inbody_path), key_cols=["date"])
        if not merged.empty:
            merged.to_csv(inbody_path, index=False)
        report.rows_added_inbody = added

    # ── Append to import_log.csv ─────────────────────────────────────
    log_rows = report.as_log_rows()
    if log_rows and import_log_path.exists():
        existing = pd.read_csv(import_log_path)
        combined = pd.concat([existing, pd.DataFrame(log_rows)], ignore_index=True)
        combined.to_csv(import_log_path, index=False)

    return report


def last_sync_age_hours() -> Optional[float]:
    """How long since the last successful Health Auto Export sync, in hours.

    Reads ``import_log.csv`` for the most recent ``source_type ==
    healthkit_json`` row. Returns None if there's no history.

    Used by the watchlist freshness check.
    """
    import_log_path = Path("protocl/data/ryan/import_log.csv")
    if not import_log_path.exists():
        return None
    try:
        log = pd.read_csv(import_log_path)
    except Exception:
        return None
    hk = log[log["source_type"] == "healthkit_json"]
    if hk.empty:
        return None
    last_ts = pd.to_datetime(hk["timestamp"].iloc[-1], errors="coerce", utc=True)
    if pd.isna(last_ts):
        return None
    delta = pd.Timestamp.now(tz="UTC") - last_ts
    return delta.total_seconds() / 3600.0
