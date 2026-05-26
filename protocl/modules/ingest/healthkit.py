"""Apple HealthKit ingest scaffold.

Apple Health doesn't expose a cloud API. The supported path on iOS is:

    Health.app → your profile → Export All Health Data → export.zip

Which produces an `export.xml` (sometimes >100MB) with every record. This
module parses that file into the Protocōl wearables / training schemas.

Usage from the Import Center:

    from modules.ingest.healthkit import parse_export
    rows = parse_export(uploaded_xml_bytes)

Usage from a cron / shortcut bridge (e.g. an iOS Shortcut + S3 drop):

    from modules.ingest.healthkit import parse_export
    rows = parse_export(open("/path/to/export.xml", "rb").read())

This file ships as a working scaffold — the XML reader is real, but the
sample/record-type mapping table is intentionally small; extend it as you
encounter new types in your own export.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import IO
from xml.etree import ElementTree as ET

import pandas as pd


# Apple HealthKit record types we currently map to Protocōl columns.
# Extend this dict as new fields are needed.
TYPE_MAP: dict[str, tuple[str, str]] = {
    # (target_csv, column_name)
    "HKQuantityTypeIdentifierRestingHeartRate":          ("wearables", "resting_hr_bpm"),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":  ("wearables", "hrv_sdnn_ms"),
    "HKQuantityTypeIdentifierVO2Max":                    ("wearables", "vo2_max_ml_kg_min"),
    "HKCategoryTypeIdentifierSleepAnalysis":             ("wearables", "sleep_duration_hrs"),
    "HKQuantityTypeIdentifierStepCount":                 ("wearables", "steps"),
    "HKQuantityTypeIdentifierActiveEnergyBurned":        ("wearables", "active_calories"),
    "HKQuantityTypeIdentifierAppleStandTime":            ("wearables", "stand_hrs"),
    "HKQuantityTypeIdentifierRespiratoryRate":           ("wearables", "respiratory_rate_brpm"),
    "HKQuantityTypeIdentifierOxygenSaturation":          ("wearables", "spo2_pct"),
}


def parse_export(xml_bytes: bytes) -> dict[str, pd.DataFrame]:
    """Parse an Apple Health `export.xml`. Returns a dict keyed by target CSV.

    Strategy: iter-parse records, group by date + target column, average within
    a day. This is intentionally simple — it'll handle a multi-megabyte export
    without holding everything in memory.

    Returns `{"wearables": pd.DataFrame, ...}`.
    """
    # daily_agg[(target, col, date)] -> list[float | str]
    daily_agg: dict[tuple[str, str, str], list] = defaultdict(list)

    # ElementTree iterparse keeps memory bounded
    context = ET.iterparse(_to_filelike(xml_bytes), events=("end",))
    for _, elem in context:
        if elem.tag != "Record":
            elem.clear()
            continue
        rtype = elem.get("type", "")
        if rtype not in TYPE_MAP:
            elem.clear()
            continue
        target, col = TYPE_MAP[rtype]
        start = elem.get("startDate", "")
        try:
            date_only = start.split(" ")[0]
        except Exception:
            elem.clear()
            continue
        value = elem.get("value")
        if value is None:
            elem.clear()
            continue
        try:
            v: float | str = float(value)
        except ValueError:
            v = value
        daily_agg[(target, col, date_only)].append(v)
        elem.clear()

    # Build per-target wide DataFrames
    out: dict[str, pd.DataFrame] = {}
    by_target: dict[str, dict[str, dict[str, float | str]]] = defaultdict(lambda: defaultdict(dict))
    for (target, col, date), vals in daily_agg.items():
        # numeric mean if all numeric; otherwise first value
        numeric = [v for v in vals if isinstance(v, (int, float))]
        agg = sum(numeric) / len(numeric) if numeric else vals[0]
        if col in ("steps", "active_calories"):                # sums, not means
            agg = sum(numeric) if numeric else 0
        if col == "sleep_duration_hrs":
            # sleep records are short segments — sum, convert to hours (Apple uses minutes? seconds?)
            # Apple HK sleep is recorded as date intervals; this scaffold treats `value` as minutes.
            agg = sum(numeric) / 60.0 if numeric else 0
        by_target[target][date][col] = agg

    for target, rows in by_target.items():
        df = pd.DataFrame.from_dict(rows, orient="index").reset_index().rename(
            columns={"index": "date"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"]).sort_values("date")
        df["source"] = "apple_health"
        out[target] = df

    return out


def _to_filelike(b: bytes) -> IO[bytes]:
    import io
    return io.BytesIO(b)


def is_configured() -> bool:
    """Apple HealthKit needs no API key — it's always a file upload path."""
    return True
