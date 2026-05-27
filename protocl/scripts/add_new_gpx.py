"""Add 5 new GPX dates to training.csv:
   2020-04-04, 2022-07-20, 2022-08-23, 2023-03-30, 2025-09-17
"""
import xml.etree.ElementTree as ET
from datetime import datetime
from math import radians, sin, cos, asin, sqrt
from pathlib import Path
import pandas as pd

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
TRAINING_CSV = Path("/home/user/workspace/protocl/protocl/data/ryan/training.csv")
LOG_CSV = Path("/home/user/workspace/protocl/protocl/data/ryan/import_log.csv")

NEW_FILES = [
    "/home/user/workspace/route_2020-04-04_1.39pm.gpx",
    "/home/user/workspace/route_2022-07-20_3.42pm.gpx",
    "/home/user/workspace/route_2022-08-23_5.59pm.gpx",
    "/home/user/workspace/route_2023-03-30_1.39pm.gpx",
    "/home/user/workspace/route_2025-09-17_3.17pm.gpx",
]


def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8  # miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return 2 * R * asin(sqrt(a))


def parse_gpx(path):
    tree = ET.parse(path)
    root = tree.getroot()
    pts = []
    for trkpt in root.findall(".//gpx:trkpt", NS):
        lat = float(trkpt.get("lat"))
        lon = float(trkpt.get("lon"))
        ele_el = trkpt.find("gpx:ele", NS)
        ele = float(ele_el.text) if ele_el is not None else None
        time_el = trkpt.find("gpx:time", NS)
        # Some GPX have export timestamps not activity timestamps — fall back to filename
        t = time_el.text if time_el is not None else None
        pts.append((lat, lon, ele, t))
    return pts


def summarize(path):
    pts = parse_gpx(path)
    if not pts:
        return None
    # Distance + elevation gain
    dist = 0.0
    elev_gain = 0.0
    for i in range(1, len(pts)):
        dist += haversine_miles(pts[i-1][0], pts[i-1][1], pts[i][0], pts[i][1])
        if pts[i][2] is not None and pts[i-1][2] is not None:
            d = pts[i][2] - pts[i-1][2]
            if d > 0:
                elev_gain += d
    elev_gain_ft = elev_gain * 3.28084
    # Duration from timestamps (when meaningful)
    duration_min = None
    times = [p[3] for p in pts if p[3]]
    if len(times) >= 2:
        try:
            t0 = datetime.fromisoformat(times[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(times[-1].replace("Z", "+00:00"))
            secs = (t1 - t0).total_seconds()
            if 60 <= secs <= 24*3600:
                duration_min = secs / 60.0
        except Exception:
            pass
    return {
        "points": len(pts),
        "distance_miles": round(dist, 2),
        "elevation_ft": round(elev_gain_ft),
        "duration_min": round(duration_min, 1) if duration_min else None,
    }


def classify(s):
    # Avg speed > 7 mph likely a ride
    if s["duration_min"]:
        speed = s["distance_miles"] / (s["duration_min"] / 60.0)
        if speed > 7:
            return "ride", round(speed, 1)
        return "walk", round(speed, 1)
    return ("ride", None) if s["distance_miles"] > 5 else ("walk", None)


def main():
    existing = pd.read_csv(TRAINING_CSV)
    new_rows = []
    for path in NEW_FILES:
        fname = Path(path).name
        # Extract date from filename: route_YYYY-MM-DD_*
        date = fname.split("_")[1]
        s = summarize(path)
        if not s:
            print(f"  SKIP empty: {fname}")
            continue
        activity, speed = classify(s)
        if s["duration_min"]:
            notes = f"avg speed {speed} mph · {s['points']} GPS points"
        else:
            notes = f"duration unavailable in GPX · {s['points']} GPS points"
        new_rows.append({
            "date": date,
            "activity_type": activity,
            "source": "apple_health_gpx",
            "duration_min": s["duration_min"] if s["duration_min"] else "",
            "distance_miles": s["distance_miles"],
            "elevation_ft": s["elevation_ft"],
            "avg_hr_bpm": "", "max_hr_bpm": "", "avg_power_watts": "",
            "avg_cadence_rpm": "", "calories": "", "tss": "", "zone2_min": "",
            "notes": notes,
        })
        print(f"  {date} {activity}: {s['distance_miles']} mi · {s['elevation_ft']} ft · {s['duration_min']} min · {s['points']} pts")
    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True).sort_values("date").reset_index(drop=True)
    combined.to_csv(TRAINING_CSV, index=False)
    print(f"\nWrote {len(combined)} training rows ({len(new_df)} new) → {TRAINING_CSV}")

    # Audit log
    ts = datetime.now().isoformat(timespec="seconds")
    log_rows = [{
        "timestamp": ts, "source_type": "training_gpx",
        "filename": Path(p).name,
        "rows_imported": 1, "rows_skipped_duplicate": 0,
        "errors": "", "imported_by": "add_new_gpx.py"
    } for p in NEW_FILES]
    log = pd.read_csv(LOG_CSV)
    log = pd.concat([log, pd.DataFrame(log_rows)], ignore_index=True)
    log.to_csv(LOG_CSV, index=False)
    print(f"Appended {len(log_rows)} import_log rows")


if __name__ == "__main__":
    main()
