"""Apple HealthKit ingest — Health Auto Export JSON format.

The companion to ``healthkit.py`` (XML export). Health Auto Export
(https://healthyapps.dev) is a paid iOS app that runs scheduled exports
of HealthKit data and pushes JSON files to Google Drive / iCloud / S3 /
REST. That makes it the only practical path to *automated, recurring*
HealthKit ingestion — Apple has no cloud API.

Schema produced by Health Auto Export v8.x::

    {
      "data": {
        "metrics": [
          {
            "name": "heart_rate",
            "units": "count/min",
            "data": [
              {"date": "2026-01-09 00:00:00 -0700",
               "source": "RyGarrett's Watch",
               "qty": 56.3}
            ]
          },
          ...
        ],
        "workouts": [...]   # optional, not currently ingested
      }
    }

Each ``metric.data[*]`` row has at minimum ``date`` and one of ``qty``,
``Avg``/``Min``/``Max`` (sleep stages), or ``totalEnergy``/``distance``
(workout-derived rows). For sleep analysis the row has named keys like
``inBed``, ``asleep``, ``rem``, ``deep`` measured in hours.

Usage::

    from modules.ingest.healthkit_json import parse_export
    payload = parse_export(open("HealthAutoExport-2026-01.json", "rb").read())
    # payload = {"wearables": DataFrame, "cgm_readings": DataFrame,
    #            "inbody": DataFrame, "skipped_metrics": [...]}

The ingester is deliberately tolerant: unknown metric names are dropped
into ``skipped_metrics`` instead of crashing, so a new Apple Health type
landing in next month's export won't break the pipeline.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable

import pandas as pd

# ─── Metric routing ───────────────────────────────────────────────────────
#
# Maps Health Auto Export `metric.name` → (target_csv, target_column,
# aggregation_strategy). Targets correspond to existing CSVs in
# ``protocl/data/ryan/``.
#
# Aggregation strategies:
#   "mean"      — average across same-day samples (e.g. heart rate)
#   "sum"       — sum across same-day samples (e.g. steps, calories)
#   "max"       — daily max (e.g. peak heart rate)
#   "last"      — last sample of the day wins (e.g. weight, body fat)
#   "minutes"   — Health Auto Export reports duration in MINUTES; convert
#                 to hours for our wearables schema (sleep, exercise time)
#
METRIC_MAP: dict[str, tuple[str, str, str]] = {
    # Wearables — daily roll-up
    "resting_heart_rate":         ("wearables", "resting_hr_bpm",        "mean"),
    "heart_rate":                 ("wearables", "avg_hr_bpm",            "mean"),
    "walking_heart_rate_average": ("wearables", "walking_hr_bpm",        "mean"),
    "heart_rate_variability":     ("wearables", "hrv_sdnn_ms",           "mean"),
    "vo2_max":                    ("wearables", "vo2_max_ml_kg_min",     "mean"),
    "respiratory_rate":           ("wearables", "respiratory_rate_brpm", "mean"),
    "blood_oxygen_saturation":    ("wearables", "spo2_pct",              "mean"),
    "step_count":                 ("wearables", "steps",                 "sum"),
    "active_energy":              ("wearables", "active_calories",       "sum"),
    "basal_energy_burned":        ("wearables", "basal_calories",        "sum"),
    "apple_stand_hour":           ("wearables", "stand_hrs",             "sum"),
    "apple_exercise_time":        ("wearables", "exercise_minutes",      "sum"),
    "flights_climbed":            ("wearables", "flights_climbed",       "sum"),
    "walking_running_distance":   ("wearables", "distance_mi",           "sum"),
    "time_in_daylight":           ("wearables", "daylight_minutes",      "sum"),
    "sleep_analysis":             ("wearables", "_sleep",                "sleep"),   # special-cased
    "apple_sleeping_wrist_temperature": ("wearables", "skin_temp_delta_f", "mean"),

    # Body composition — last sample of the day wins
    "weight_body_mass":  ("inbody", "weight_lbs",   "last"),
    "body_fat_percentage": ("inbody", "body_fat_pct", "last"),
    "body_mass_index":   ("inbody", "bmi",          "last"),

    # CGM — preserve 5-minute granularity (no aggregation)
    "blood_glucose":     ("cgm_readings", "glucose_mg_dl", "raw"),
}

# Metrics in the export that are intentionally NOT mapped today.
# Listed so we can show a clear "skipped X (no column)" log line.
KNOWN_UNMAPPED = {
    "environmental_audio_exposure",
    "headphone_audio_exposure",
    "physical_effort",
    "stair_speed_up",
    "stair_speed_down",
    "walking_asymmetry_percentage",
    "walking_double_support_percentage",
    "walking_speed",
    "walking_step_length",
    "six_minute_walking_test_distance",
    "breathing_disturbances",
    "height",  # rarely changes; ignore
}


# ─── Date parsing ─────────────────────────────────────────────────────────

# Health Auto Export emits "2026-01-09 00:00:00 -0700".
# Python <3.11's fromisoformat doesn't accept that format, so we hand-parse.
_DATE_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<tz>[+-]\d{4})$"
)


def parse_hae_datetime(s: str) -> pd.Timestamp | None:
    """Parse a Health Auto Export date string to a timezone-aware Timestamp.

    Returns the timestamp in America/Denver. ``None`` on failure.
    """
    if not s:
        return None
    m = _DATE_RE.match(s.strip())
    if not m:
        # Some exports omit timezone — try plain ISO
        try:
            return pd.Timestamp(s).tz_localize("America/Denver")
        except Exception:
            return None
    iso = f"{m['date']}T{m['time']}{m['tz'][:3]}:{m['tz'][3:]}"
    try:
        return pd.Timestamp(iso).tz_convert("America/Denver")
    except Exception:
        return None


# ─── Core ingest ──────────────────────────────────────────────────────────

@dataclass
class IngestResult:
    """What ``parse_export`` returns. Lightweight wrapper around DataFrames
    so callers can inspect counts and skipped metrics without re-parsing."""
    wearables: pd.DataFrame
    cgm_readings: pd.DataFrame
    inbody: pd.DataFrame
    skipped_metrics: list[str] = field(default_factory=list)
    rows_in: int = 0
    rows_out: int = 0

    def as_dict(self) -> dict[str, pd.DataFrame]:
        """Mirror the XML ingester's return signature for drop-in use."""
        return {
            "wearables": self.wearables,
            "cgm_readings": self.cgm_readings,
            "inbody": self.inbody,
        }


def parse_export(json_bytes: bytes) -> IngestResult:
    """Parse a Health Auto Export JSON payload.

    Tolerates: unknown metric names, missing values, malformed dates,
    mixed-source same-day samples, sparse metrics. Crashes only on
    malformed JSON at the top level (intentional — we want to know).
    """
    if isinstance(json_bytes, (bytes, bytearray)):
        text = json_bytes.decode("utf-8")
    else:
        text = json_bytes
    payload = json.loads(text)

    metrics = (payload.get("data") or {}).get("metrics") or []
    rows_in = 0
    skipped: list[str] = []

    # Aggregation buckets keyed by (target, date_str, column) → list[float]
    daily: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    daily_strategy: dict[tuple[str, str, str], str] = {}
    daily_source: dict[tuple[str, str, str], str] = {}

    # Sleep needs its own per-day struct because each sample row carries
    # multiple keyed quantities (inBed, asleep, rem, deep).
    sleep_daily: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    sleep_source: dict[str, str] = {}

    # CGM rows are NOT aggregated — preserve the raw stream.
    cgm_rows: list[dict[str, Any]] = []

    for metric in metrics:
        name = metric.get("name", "")
        samples = metric.get("data") or []
        rows_in += len(samples)

        if name not in METRIC_MAP:
            if name and name not in KNOWN_UNMAPPED:
                skipped.append(name)
            continue

        target, col, strategy = METRIC_MAP[name]

        for sample in samples:
            ts = parse_hae_datetime(sample.get("date", ""))
            if ts is None:
                continue
            src = sample.get("source", "apple_health") or "apple_health"

            # ── CGM: keep every sample ────────────────────────────────
            if strategy == "raw":
                qty = sample.get("qty")
                if qty is None:
                    continue
                try:
                    mg_dl = float(qty)
                except (TypeError, ValueError):
                    continue
                cgm_rows.append({
                    "datetime": ts.tz_localize(None).isoformat(timespec="seconds"),
                    "glucose_mg_dl": round(mg_dl, 1),
                    "glucose_mmol_l": round(mg_dl / 18.0182, 2),
                    "source": src,
                    "sensor_type": "cgm",
                    "notes": "",
                })
                continue

            # ── Sleep: keyed stages, not a single qty ────────────────
            if strategy == "sleep":
                date_str = ts.strftime("%Y-%m-%d")
                # Health Auto Export reports sleep stages in HOURS already
                for stage_key, target_col in (
                    ("asleep",  "sleep_duration_hrs"),
                    ("deep",    "sleep_deep_hrs"),
                    ("rem",     "sleep_rem_hrs"),
                ):
                    v = sample.get(stage_key)
                    if v is not None:
                        try:
                            sleep_daily[date_str][target_col] += float(v)
                        except (TypeError, ValueError):
                            pass
                sleep_source[date_str] = src
                continue

            # ── Standard daily metrics ───────────────────────────────
            qty = sample.get("qty")
            if qty is None:
                continue
            try:
                v = float(qty)
            except (TypeError, ValueError):
                continue
            date_str = ts.strftime("%Y-%m-%d")
            key = (target, date_str, col)
            daily[key].append(v)
            daily_strategy[key] = strategy
            daily_source[key] = src

    # ── Reduce buckets into wide DataFrames ──────────────────────────
    by_target: dict[str, dict[str, dict[str, Any]]] = {
        "wearables": defaultdict(dict),
        "inbody":    defaultdict(dict),
    }
    for (target, date_str, col), values in daily.items():
        strategy = daily_strategy[(target, date_str, col)]
        if not values:
            continue
        if strategy == "mean":
            agg = sum(values) / len(values)
        elif strategy == "sum":
            agg = sum(values)
        elif strategy == "max":
            agg = max(values)
        elif strategy == "last":
            agg = values[-1]
        else:
            agg = values[0]
        # Round numeric outputs to keep CSVs human-readable
        if isinstance(agg, float):
            agg = round(agg, 2)
        by_target[target][date_str][col] = agg
        by_target[target][date_str].setdefault("source", daily_source[(target, date_str, col)])

    # Merge sleep into wearables
    for date_str, stages in sleep_daily.items():
        for k, v in stages.items():
            by_target["wearables"][date_str][k] = round(v, 2)
        by_target["wearables"][date_str].setdefault("source", sleep_source.get(date_str, "apple_health"))

    wearables_df = _rows_to_df(by_target["wearables"], date_col="date")
    inbody_df    = _rows_to_df(by_target["inbody"],    date_col="date")
    cgm_df       = pd.DataFrame(cgm_rows)
    if not cgm_df.empty:
        cgm_df = cgm_df.sort_values("datetime").reset_index(drop=True)

    rows_out = len(wearables_df) + len(inbody_df) + len(cgm_df)
    return IngestResult(
        wearables=wearables_df,
        cgm_readings=cgm_df,
        inbody=inbody_df,
        skipped_metrics=sorted(set(skipped)),
        rows_in=rows_in,
        rows_out=rows_out,
    )


def _rows_to_df(rows: dict[str, dict[str, Any]], *, date_col: str) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(rows, orient="index").reset_index()
    df = df.rename(columns={"index": date_col})
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).sort_values(date_col).reset_index(drop=True)
    df[date_col] = df[date_col].dt.strftime("%Y-%m-%d")
    return df


# ─── Merging into existing CSVs ───────────────────────────────────────────

def merge_into_csv(
    new: pd.DataFrame,
    existing_path: str,
    *,
    key_cols: list[str],
) -> tuple[pd.DataFrame, int, int]:
    """De-dupe new rows against an existing CSV and return the merged frame.

    Returns ``(merged_df, rows_added, rows_skipped_dup)``. Caller decides
    when to write to disk.
    """
    import os
    if new is None or new.empty:
        if os.path.exists(existing_path):
            return pd.read_csv(existing_path), 0, 0
        return pd.DataFrame(), 0, 0

    if not os.path.exists(existing_path):
        return new.copy(), len(new), 0

    existing = pd.read_csv(existing_path)
    # Sentinel: drop any rows in existing with the same keys as new — new wins
    if all(k in existing.columns for k in key_cols) and all(k in new.columns for k in key_cols):
        before = len(existing)
        existing_keys = existing[key_cols].apply(tuple, axis=1)
        new_keys = set(new[key_cols].apply(tuple, axis=1).tolist())
        existing = existing[~existing_keys.isin(new_keys)]
        dupes = before - len(existing)
    else:
        dupes = 0

    # Concatenate; for columns missing on one side, fill NaN
    merged = pd.concat([existing, new], ignore_index=True, sort=False)
    if key_cols and all(k in merged.columns for k in key_cols):
        merged = merged.sort_values(key_cols).reset_index(drop=True)
    added = len(new)
    return merged, added, dupes


def is_configured() -> bool:
    """JSON ingest is a pure-Python path — always available."""
    return True
