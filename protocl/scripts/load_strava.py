"""
load_strava.py — Pull Strava activities, dedupe vs Apple Healthkit/GPX, merge into training.csv

Reads from: protocl/data/ryan/_strava_raw.json (saved from the strava connector)
Writes to:  protocl/data/ryan/training.csv (merged) + protocl/data/ryan/import_log.csv (audit)

Dedup rule:
  - For each Strava activity, check if a row already exists in training.csv with:
      same date AND
      same normalized activity_type AND
      duration within ±10% (or both within ±2 min if total <30 min)
  - If match found, ENRICH that row with HR/power/cadence/tss from Strava (don't duplicate).
  - If no match, ADD as new row with source='strava'.

Strava-specific:
  - distance: meters → miles (× 0.000621371)
  - elevation_gain: meters → feet (× 3.28084)
  - moving_time: seconds → minutes
  - tss proxy: Strava 'suffer_score' (Relative Effort) — closest free proxy without zone calc
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# --- Paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
RAW_JSON = ROOT / "data" / "ryan" / "_strava_raw.json"
TRAINING_CSV = ROOT / "data" / "ryan" / "training.csv"
IMPORT_LOG_CSV = ROOT / "data" / "ryan" / "import_log.csv"

# --- Mappings --------------------------------------------------------------
# Strava sport_type → our internal activity_type (must match what's already in training.csv)
SPORT_TYPE_MAP = {
    "MountainBikeRide": "mtb",
    "Ride": "ride",
    "EBikeRide": "ebike",
    "VirtualRide": "ride",
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Walk": "walk",
    "Hike": "hike",
    "WeightTraining": "strength",
    "Workout": "workout",
    "HighIntensityIntervalTraining": "hiit",
    "Yoga": "yoga",
    "Pilates": "pilates",
    "Elliptical": "elliptical",
    "StairStepper": "stair",
    "Swim": "swim",
    "Rowing": "row",
    "Basketball": "basketball",
    "Crossfit": "crossfit",
    "Soccer": "soccer",
}

# Map our HK activity_type names → strava-equivalent for dedup matching
# (these are activity_type values currently in training.csv from HK + GPX)
HK_TO_STRAVA_EQUIV = {
    "ride": ["ride", "mtb", "ebike"],
    "mtb": ["mtb", "ride"],
    "ebike": ["ebike", "ride"],
    "walk": ["walk"],
    "run": ["run"],
    "hike": ["hike", "walk"],
    "strength": ["strength", "workout"],
    "workout": ["workout", "strength", "hiit"],
    "hiit": ["hiit", "workout"],
    "yoga": ["yoga"],
    "core": ["workout", "core"],
    "elliptical": ["elliptical"],
    "swim": ["swim"],
    "row": ["row"],
    "basketball": ["basketball"],
}

M_TO_MI = 0.000621371
M_TO_FT = 3.28084


def normalize_strava(act: dict) -> dict:
    """Normalize a Strava activity dict to our training.csv row schema."""
    sport = act.get("sport_type") or act.get("type", "Workout")
    activity_type = SPORT_TYPE_MAP.get(sport, sport.lower())

    duration_min = round((act.get("moving_time") or 0) / 60.0, 1) or None
    distance_mi = round((act.get("distance") or 0) * M_TO_MI, 2) or None
    elev_ft = round((act.get("total_elevation_gain") or 0) * M_TO_FT, 0) or None

    avg_hr = act.get("average_heartrate") if act.get("has_heartrate") else None
    max_hr = act.get("max_heartrate") if act.get("has_heartrate") else None
    avg_w = act.get("average_watts")
    avg_cad = act.get("average_cadence")
    cal = act.get("kilojoules")  # close approx for kcal on bikes (ratio ~1:1 at ~25% efficiency)
    cal = round(cal) if cal else None
    tss = act.get("suffer_score")  # Strava Relative Effort

    notes_parts = [act.get("name", "")]
    if act.get("trainer"):
        notes_parts.append("indoor")
    if act.get("device_name"):
        notes_parts.append(f"dev:{act['device_name']}")
    notes_parts.append(f"strava_id:{act['id']}")
    notes = " · ".join(p for p in notes_parts if p)

    return {
        "date": act["start_date_local"][:10],
        "activity_type": activity_type,
        "source": "strava",
        "duration_min": duration_min,
        "distance_miles": distance_mi,
        "elevation_ft": elev_ft,
        "avg_hr_bpm": round(avg_hr, 1) if avg_hr else None,
        "max_hr_bpm": int(max_hr) if max_hr else None,
        "avg_power_watts": round(avg_w, 1) if avg_w else None,
        "avg_cadence_rpm": round(avg_cad, 1) if avg_cad else None,
        "calories": cal,
        "tss": tss,
        "zone2_min": None,  # would need per-second HR streams to compute
        "notes": notes,
        "_strava_id": act["id"],
    }


def find_existing_match(
    strava_row: dict, training_df: pd.DataFrame
) -> int | None:
    """Return index of existing row that matches this strava activity, else None."""
    date = strava_row["date"]
    s_type = strava_row["activity_type"]
    s_dur = strava_row.get("duration_min")

    # Filter to same date
    same_day = training_df[training_df["date"] == date]
    if same_day.empty:
        return None

    # Check matches by activity_type equivalence
    for idx, row in same_day.iterrows():
        hk_type = row["activity_type"]
        # Are these equivalent activities?
        equivs = HK_TO_STRAVA_EQUIV.get(hk_type, [hk_type])
        if s_type not in equivs and hk_type != s_type:
            continue

        # Duration check (if both have durations)
        hk_dur = row.get("duration_min")
        if pd.notna(hk_dur) and s_dur:
            if hk_dur < 30 or s_dur < 30:
                # Short workout: ±5 min tolerance
                if abs(hk_dur - s_dur) > 5:
                    continue
            else:
                # Longer: ±15% tolerance
                if abs(hk_dur - s_dur) / max(hk_dur, s_dur) > 0.15:
                    continue
        # if either missing duration, accept match on date+type alone
        return idx

    return None


def enrich_existing(training_df: pd.DataFrame, idx: int, strava_row: dict) -> dict:
    """Backfill missing fields in existing row from Strava data. Returns dict of fields updated."""
    updated = {}
    enrich_fields = [
        "duration_min", "distance_miles", "elevation_ft",
        "avg_hr_bpm", "max_hr_bpm", "avg_power_watts",
        "avg_cadence_rpm", "calories", "tss",
    ]
    for f in enrich_fields:
        existing = training_df.at[idx, f]
        new_val = strava_row.get(f)
        if pd.isna(existing) and new_val is not None:
            training_df.at[idx, f] = new_val
            updated[f] = new_val

    # Tag the source with strava-enriched and append strava_id to notes
    existing_notes = training_df.at[idx, "notes"]
    existing_notes = "" if pd.isna(existing_notes) else str(existing_notes)
    if f"strava_id:{strava_row['_strava_id']}" not in existing_notes:
        sep = " · " if existing_notes else ""
        training_df.at[idx, "notes"] = (
            f"{existing_notes}{sep}strava_id:{strava_row['_strava_id']}"
        )
        updated["notes"] = "tagged"

    # Bump source to indicate enrichment
    cur_src = training_df.at[idx, "source"]
    if "strava" not in str(cur_src):
        training_df.at[idx, "source"] = f"{cur_src}+strava"
        updated["source"] = training_df.at[idx, "source"]
    return updated


def main():
    print(f"Loading raw Strava data from {RAW_JSON}")
    with open(RAW_JSON) as f:
        raw = json.load(f)
    acts = raw["result"]
    print(f"  {len(acts)} activities pulled\n")

    print(f"Loading existing training.csv from {TRAINING_CSV}")
    training_df = pd.read_csv(TRAINING_CSV)
    print(f"  {len(training_df)} existing rows\n")

    new_rows = []
    enriched_count = 0
    enriched_details = []
    skipped_already_strava = 0

    for act in acts:
        srow = normalize_strava(act)
        sid = srow["_strava_id"]

        # If this strava_id already in any row's notes, skip
        already_tagged = training_df["notes"].fillna("").str.contains(
            f"strava_id:{sid}", regex=False
        )
        if already_tagged.any():
            skipped_already_strava += 1
            continue

        match_idx = find_existing_match(srow, training_df)
        if match_idx is not None:
            updated = enrich_existing(training_df, match_idx, srow)
            if updated:
                enriched_count += 1
                enriched_details.append(
                    f"  {srow['date']} {srow['activity_type']} → "
                    f"enriched row {match_idx} ({', '.join(updated.keys())})"
                )
        else:
            # New row — drop the helper field
            srow_clean = {k: v for k, v in srow.items() if not k.startswith("_")}
            new_rows.append(srow_clean)

    print(f"Enriched {enriched_count} existing rows:")
    for d in enriched_details[:20]:
        print(d)
    if len(enriched_details) > 20:
        print(f"  ... +{len(enriched_details) - 20} more")

    print(f"\nAdding {len(new_rows)} brand-new Strava rows")
    print(f"Skipped {skipped_already_strava} (already had strava_id tag)")

    if new_rows:
        new_df = pd.DataFrame(new_rows)
        # Align columns
        for col in training_df.columns:
            if col not in new_df.columns:
                new_df[col] = None
        new_df = new_df[training_df.columns]
        training_df = pd.concat([training_df, new_df], ignore_index=True)

    training_df = training_df.sort_values("date").reset_index(drop=True)
    training_df.to_csv(TRAINING_CSV, index=False)
    print(f"\nWrote {len(training_df)} rows to {TRAINING_CSV}")

    # Append to import_log.csv (canonical 7-col schema)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    log_row = pd.DataFrame([{
        "timestamp": ts,
        "source_type": "strava_api",
        "filename": "training.csv (+strava)",
        "rows_imported": len(new_rows) + enriched_count,
        "rows_skipped_duplicate": skipped_already_strava,
        "errors": "",
        "imported_by": "load_strava.py",
    }])
    if IMPORT_LOG_CSV.exists():
        log_df = pd.read_csv(IMPORT_LOG_CSV)
        log_df = pd.concat([log_df, log_row], ignore_index=True)
    else:
        log_df = log_row
    log_df.to_csv(IMPORT_LOG_CSV, index=False)
    print(f"Stamped import_log.csv ({len(log_df)} entries)")

    # Quick stats
    print(f"\n--- Training.csv post-merge stats ---")
    print(f"Total rows: {len(training_df)}")
    print(f"With avg_hr_bpm: {training_df['avg_hr_bpm'].notna().sum()}")
    print(f"With avg_power_watts: {training_df['avg_power_watts'].notna().sum()}")
    print(f"With avg_cadence_rpm: {training_df['avg_cadence_rpm'].notna().sum()}")
    print(f"With tss (Relative Effort): {training_df['tss'].notna().sum()}")
    print(f"Source mix: {training_df['source'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
