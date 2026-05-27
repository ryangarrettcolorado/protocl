"""Load Apple HealthKit connector payloads into wearables.csv + training.csv.

Source: two JSON blobs from the apple_healthkit connector (saved in current_session_context).
Outputs:
  - wearables.csv (date,resting_hr_bpm,hrv_sdnn_ms,sleep_duration_hrs,sleep_deep_hrs,sleep_rem_hrs,active_calories,steps,source)
  - training.csv (append 81 workouts, dedupe against existing 11 GPX rows by date+activity_type)
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import pandas as pd

OUTPUTS = "/home/user/workspace/current_session_context/tool_calls/call_external_tool/"
PAYLOAD_A = Path(OUTPUTS) / "output_mpnekswl.json"  # RHR, HRV, steps, energy, body mass
PAYLOAD_B = Path(OUTPUTS) / "output_mpnel2bc.json"  # distance, flights, workouts, sleep

WEARABLES_CSV = Path("/home/user/workspace/protocl/protocl/data/ryan/wearables.csv")
TRAINING_CSV  = Path("/home/user/workspace/protocl/protocl/data/ryan/training.csv")
LOG_CSV       = Path("/home/user/workspace/protocl/protocl/data/ryan/import_log.csv")

TZ = "America/Denver"


def unwrap(path):
    d = json.load(open(path))
    text = d['client_result']['result'][0]['text']
    return json.loads(text)


def to_local_date(iso_utc, anchor="end"):
    """Convert UTC ISO -> America/Denver date (YYYY-MM-DD)."""
    # Apple gives ISO 8601 UTC; convert to MDT (-6) / MST (-7). Use pandas for DST handling.
    return pd.Timestamp(iso_utc).tz_convert(TZ).strftime("%Y-%m-%d")


def daily_avg(entries):
    """For discreteAverage quantities (RHR, HRV). Returns {date: value}."""
    out = {}
    for e in entries:
        d = to_local_date(e['endDate'])
        v = e['value']['payload']['value']
        out[d] = round(v, 1)
    return out


def daily_sum(entries):
    """For cumulativeSum quantities (steps, distance, flights, energy)."""
    out = {}
    for e in entries:
        d = to_local_date(e['endDate'])
        v = e['value']['payload']['value']
        out[d] = round(v, 1)
    return out


def aggregate_sleep(entries):
    """Group sleep stages by 'sleep night' (anchored to the morning the sleep ends).
    Returns {date: {duration_hrs, deep_hrs, rem_hrs}}.
    Stage values: 0=InBed, 1=Asleep(legacy), 2=Awake, 3=Core, 4=Deep, 5=REM
    """
    nights = defaultdict(lambda: {"asleep_min": 0.0, "deep_min": 0.0, "rem_min": 0.0})
    for e in entries:
        stage = e['value']['payload']['value']
        start = pd.Timestamp(e['startDate'])
        end = pd.Timestamp(e['endDate'])
        duration_min = (end - start).total_seconds() / 60.0
        # Anchor to local wake date (end time, local)
        wake_date = end.tz_convert(TZ).strftime("%Y-%m-%d")
        if stage in (1, 3, 4, 5):  # asleep-equivalent stages
            nights[wake_date]["asleep_min"] += duration_min
        if stage == 4:
            nights[wake_date]["deep_min"] += duration_min
        if stage == 5:
            nights[wake_date]["rem_min"] += duration_min
    return {d: {
        "sleep_duration_hrs": round(v["asleep_min"] / 60.0, 2),
        "sleep_deep_hrs":     round(v["deep_min"]   / 60.0, 2),
        "sleep_rem_hrs":      round(v["rem_min"]    / 60.0, 2),
    } for d, v in nights.items()}


def workouts_to_rows(workouts):
    """Convert Apple Workout entries -> training.csv rows."""
    activity_map = {
        "Walking": "walk", "Cycling": "ride", "Running": "run",
        "TraditionalStrengthTraining": "strength", "FunctionalStrengthTraining": "strength",
        "HighIntensityIntervalTraining": "hiit", "CoreTraining": "core",
        "Yoga": "yoga", "Hiking": "hike", "Other": "other",
    }
    rows = []
    for w in workouts:
        p = w['value']['payload']
        end_local = pd.Timestamp(w['endDate']).tz_convert(TZ)
        date = end_local.strftime("%Y-%m-%d")
        atype_raw = p.get('activityType', 'Other')
        atype = activity_map.get(atype_raw, atype_raw.lower())
        duration_min = round(p.get('durationSec', 0) / 60.0, 1)
        dist_mi = round((p.get('totalDistanceMeters') or 0) / 1609.344, 2) if p.get('totalDistanceMeters') else ""
        cals = round(p.get('totalEnergyKilocalories') or 0, 0) if p.get('totalEnergyKilocalories') else ""
        rows.append({
            "date": date,
            "activity_type": atype,
            "source": "apple_healthkit",
            "duration_min": duration_min,
            "distance_miles": dist_mi,
            "elevation_ft": "",
            "avg_hr_bpm": "", "max_hr_bpm": "",
            "avg_power_watts": "", "avg_cadence_rpm": "",
            "calories": cals, "tss": "", "zone2_min": "",
            "notes": f"raw type: {atype_raw}",
        })
    return rows


def main():
    a = unwrap(PAYLOAD_A)
    b = unwrap(PAYLOAD_B)

    rhr  = daily_avg(a.get("HKQuantityTypeIdentifierRestingHeartRate", []))
    hrv  = daily_avg(a.get("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", []))
    steps = daily_sum(a.get("HKQuantityTypeIdentifierStepCount", []))
    energy = daily_sum(a.get("HKQuantityTypeIdentifierActiveEnergyBurned", []))
    body_mass = a.get("HKQuantityTypeIdentifierBodyMass", [])

    sleep = aggregate_sleep(b.get("HKCategoryTypeIdentifierSleepAnalysis", []))
    workouts_raw = b.get("HKWorkoutTypeIdentifier", [])

    print(f"RHR days:    {len(rhr)}")
    print(f"HRV days:    {len(hrv)}")
    print(f"Steps days:  {len(steps)}")
    print(f"Energy days: {len(energy)}")
    print(f"Sleep nights:{len(sleep)}")
    print(f"Workouts:    {len(workouts_raw)}")
    if body_mass:
        bm_kg = body_mass[-1]['value']['payload']['value']
        print(f"Body mass (latest): {bm_kg:.1f} kg ({bm_kg*2.20462:.1f} lb)")

    # Union all dates
    all_dates = sorted(set(rhr) | set(hrv) | set(steps) | set(energy) | set(sleep))
    print(f"Union date range: {all_dates[0]} → {all_dates[-1]} ({len(all_dates)} days)")

    rows = []
    for d in all_dates:
        sd = sleep.get(d, {})
        rows.append({
            "date": d,
            "resting_hr_bpm": rhr.get(d, ""),
            "hrv_sdnn_ms": hrv.get(d, ""),
            "vo2_max_ml_kg_min": "",
            "sleep_duration_hrs": sd.get("sleep_duration_hrs", ""),
            "sleep_deep_hrs":     sd.get("sleep_deep_hrs", ""),
            "sleep_rem_hrs":      sd.get("sleep_rem_hrs", ""),
            "sleep_consistency_pct": "",
            "respiratory_rate_brpm": "",
            "spo2_pct": "",
            "active_calories": energy.get(d, ""),
            "steps": steps.get(d, ""),
            "stand_hrs": "",
            "skin_temp_delta_f": "",
            "source": "apple_healthkit",
        })

    wear_df = pd.DataFrame(rows)
    wear_df.to_csv(WEARABLES_CSV, index=False)
    print(f"\n✓ Wrote {len(wear_df)} wearable rows → {WEARABLES_CSV}")

    # Training: merge workouts, dedupe vs existing GPX rows by (date, activity_type)
    existing_train = pd.read_csv(TRAINING_CSV)
    workout_rows = workouts_to_rows(workouts_raw)
    new_workouts = pd.DataFrame(workout_rows)

    # Dedupe: don't duplicate a date+activity that's already in training from GPX
    existing_keys = set(zip(existing_train["date"], existing_train["activity_type"]))
    new_workouts["_key"] = list(zip(new_workouts["date"], new_workouts["activity_type"]))
    deduped = new_workouts[~new_workouts["_key"].isin(existing_keys)].drop(columns=["_key"])
    print(f"Workouts kept after dedupe: {len(deduped)} / {len(workout_rows)} (skipped {len(workout_rows)-len(deduped)} dupes of GPX)")

    combined_train = pd.concat([existing_train, deduped], ignore_index=True).sort_values("date").reset_index(drop=True)
    combined_train.to_csv(TRAINING_CSV, index=False)
    print(f"✓ Wrote {len(combined_train)} training rows ({len(deduped)} new from HK) → {TRAINING_CSV}")

    # Audit log
    ts = datetime.now().isoformat(timespec="seconds")
    log_rows = [
        {"timestamp": ts, "source_type": "apple_healthkit_connector",
         "filename": "rhr+hrv+steps+energy+bodymass",
         "rows_imported": len(wear_df), "rows_skipped_duplicate": 0,
         "errors": "", "imported_by": "load_apple_health.py"},
        {"timestamp": ts, "source_type": "apple_healthkit_connector",
         "filename": "sleep+workouts+distance+flights",
         "rows_imported": len(deduped), "rows_skipped_duplicate": len(workout_rows) - len(deduped),
         "errors": "", "imported_by": "load_apple_health.py"},
    ]
    log = pd.read_csv(LOG_CSV)
    log = pd.concat([log, pd.DataFrame(log_rows)], ignore_index=True)
    log.to_csv(LOG_CSV, index=False)
    print(f"✓ Appended {len(log_rows)} import_log rows")


if __name__ == "__main__":
    main()
