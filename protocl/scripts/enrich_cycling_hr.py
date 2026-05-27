"""
enrich_cycling_hr.py — Backfill avg_hr / max_hr on cycling rows by aggregating
Apple Health hourly heart-rate buckets over each ride's time window.

Why this exists:
  Strava drops the Apple Watch HR stream when the iPhone Strava app owns the
  GPS recording. The Apple Health connector returns only Workout records
  (which themselves don't carry HR aggregates) plus a separate Heart Rate
  time series. So we pull the HR series at 1-hour resolution for the past
  year and aggregate it over each ride window in training.csv.

Inputs:
  - /home/user/workspace/current_session_context/tool_calls/call_external_tool/output_mpng0qcy.json
    (full HR hourly time series for the past year)
  - protocl/data/ryan/training.csv

Output:
  - Updates training.csv: avg_hr_bpm and max_hr_bpm filled for cycling rows
    where the activity timestamp overlaps the hourly HR buckets.
  - Stamps import_log.csv with 'apple_healthkit_connector' / 'hr_backfill'.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

# --- Config ----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TRAINING_CSV = ROOT / "data" / "ryan" / "training.csv"
STRAVA_RAW = ROOT / "data" / "ryan" / "_strava_raw.json"
IMPORT_LOG = ROOT / "data" / "ryan" / "import_log.csv"

# Default HR raw path. Override via HR_RAW env var.
# Cron job should write the connector response here before invoking this script.
DEFAULT_HR_RAW = ROOT / "data" / "ryan" / "_hr_raw.json"
HR_RAW = Path(os.environ.get("HR_RAW", str(DEFAULT_HR_RAW)))

CYCLING_TYPES = {"mtb", "ride", "ebike"}


def load_hr_series() -> pd.DataFrame:
    """Parse the HK connector JSON dump into a DataFrame of hourly HR points."""
    if not HR_RAW.exists():
        print(f"HR raw file not found at {HR_RAW} — skipping HR enrichment.")
        sys.exit(0)
    with open(HR_RAW) as f:
        raw = json.load(f)
    # Connector returns either {client_result:{result:[{type:'text',text:'<json>'}]}}
    # or {result:[{type:'text',text:'<json>'}]} depending on which envelope ran.
    if "client_result" in raw:
        text_blob = raw["client_result"]["result"][0]["text"]
    else:
        text_blob = raw["result"][0]["text"]
    inner = json.loads(text_blob)
    points = inner["HKQuantityTypeIdentifierHeartRate"]
    rows = []
    for p in points:
        rows.append({
            "start_utc": pd.to_datetime(p["startDate"], utc=True),
            "end_utc": pd.to_datetime(p["endDate"], utc=True),
            "hr": p["value"]["payload"]["value"],
        })
    df = pd.DataFrame(rows).sort_values("start_utc").reset_index(drop=True)
    if df.empty:
        print("HR series empty.")
        return df
    print(f"Loaded {len(df)} hourly HR points "
          f"({df['start_utc'].min()} → {df['end_utc'].max()})")
    return df


def load_strava_windows() -> dict[int, dict]:
    """Map strava_id → {start_utc, end_utc} for every cycling activity."""
    with open(STRAVA_RAW) as f:
        raw = json.load(f)
    acts = raw["result"]
    out = {}
    for a in acts:
        if a["sport_type"] not in ("MountainBikeRide", "Ride", "EBikeRide"):
            continue
        start = pd.to_datetime(a["start_date"], utc=True)
        end = start + timedelta(seconds=a["elapsed_time"])
        out[a["id"]] = {"start_utc": start, "end_utc": end,
                         "name": a.get("name", ""),
                         "moving_min": a["moving_time"] / 60}
    print(f"Loaded {len(out)} Strava cycling activity windows")
    return out


def aggregate_hr_for_window(hr_df: pd.DataFrame, start_utc, end_utc) -> tuple[float | None, float | None]:
    """Return (avg_hr, max_hr) from hourly buckets that overlap the ride window."""
    overlap = hr_df[(hr_df["end_utc"] > start_utc) & (hr_df["start_utc"] < end_utc)]
    if overlap.empty:
        return None, None
    # Weight each bucket by the seconds of overlap with the ride window
    weights = []
    values = []
    for _, row in overlap.iterrows():
        bucket_start = max(row["start_utc"], start_utc)
        bucket_end = min(row["end_utc"], end_utc)
        secs = (bucket_end - bucket_start).total_seconds()
        if secs <= 0:
            continue
        weights.append(secs)
        values.append(row["hr"])
    if not values:
        return None, None
    avg = sum(v * w for v, w in zip(values, weights)) / sum(weights)
    mx = max(values)
    return round(avg, 1), round(mx, 1)


def main():
    hr_df = load_hr_series()
    windows = load_strava_windows()

    training_df = pd.read_csv(TRAINING_CSV, parse_dates=["date"])
    print(f"Loaded {len(training_df)} training rows")

    # Build strava_id → row index map from notes
    strava_id_to_idx = {}
    sid_re = re.compile(r"strava_id:(\d+)")
    for idx, row in training_df.iterrows():
        notes = "" if pd.isna(row["notes"]) else str(row["notes"])
        for m in sid_re.finditer(notes):
            strava_id_to_idx[int(m.group(1))] = idx

    updated = 0
    skipped_have_hr = 0
    skipped_no_window = 0
    skipped_no_overlap = 0

    for sid, win in windows.items():
        idx = strava_id_to_idx.get(sid)
        if idx is None:
            skipped_no_window += 1
            continue
        # Only fill cycling rows missing avg_hr
        if training_df.at[idx, "activity_type"] not in CYCLING_TYPES:
            continue
        if pd.notna(training_df.at[idx, "avg_hr_bpm"]):
            skipped_have_hr += 1
            continue
        avg, mx = aggregate_hr_for_window(hr_df, win["start_utc"], win["end_utc"])
        if avg is None:
            skipped_no_overlap += 1
            continue
        training_df.at[idx, "avg_hr_bpm"] = avg
        training_df.at[idx, "max_hr_bpm"] = mx
        # Tag the notes
        n = "" if pd.isna(training_df.at[idx, "notes"]) else str(training_df.at[idx, "notes"])
        if "hr:hk-hourly" not in n:
            training_df.at[idx, "notes"] = (n + " · hr:hk-hourly").strip(" ·")
        updated += 1
        print(f"  {training_df.at[idx,'date'].date()} · sid {sid} "
              f"({win['moving_min']:.0f}min) → HR avg {avg}, max {mx}")

    training_df.to_csv(TRAINING_CSV, index=False)
    print(f"\nUpdated {updated} cycling rows with HR")
    print(f"  skipped (already had HR): {skipped_have_hr}")
    print(f"  skipped (no matching row): {skipped_no_window}")
    print(f"  skipped (no HR overlap): {skipped_no_overlap}")

    # Stamp log
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    log_row = pd.DataFrame([{
        "timestamp": ts,
        "source_type": "apple_healthkit_connector",
        "filename": "heart_rate hourly → training.csv cycling rows",
        "rows_imported": updated,
        "rows_skipped_duplicate": skipped_have_hr,
        "errors": "",
        "imported_by": "enrich_cycling_hr.py",
    }])
    if IMPORT_LOG.exists():
        log_df = pd.read_csv(IMPORT_LOG)
        log_df = pd.concat([log_df, log_row], ignore_index=True)
    else:
        log_df = log_row
    log_df.to_csv(IMPORT_LOG, index=False)

    # Final stats
    cyc = training_df[training_df["activity_type"].isin(CYCLING_TYPES)]
    print(f"\nCycling HR coverage after enrichment: "
          f"{cyc['avg_hr_bpm'].notna().sum()} / {len(cyc)} rows "
          f"({cyc['avg_hr_bpm'].notna().sum() / len(cyc) * 100:.0f}%)")


if __name__ == "__main__":
    main()
