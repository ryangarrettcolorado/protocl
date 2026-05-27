"""
daily_sync.py — Combined Strava + Apple Health HR daily refresh.

Designed to be invoked by the cron job. Runs:
  1. load_strava.py — pull Strava activities, dedupe vs HK/GPX, update training.csv
  2. dedupe_cycling.py — merge same-day HK+Strava cycling duplicates
  3. enrich_cycling_hr.py — backfill HR for cycling rows missing it

Assumes:
  - data/ryan/_strava_raw.json has been populated by the cron before this runs
  - data/ryan/_hr_raw.json has been populated by the cron before this runs
    (set HR_RAW env var to override the default path)
"""
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

def run(script: str) -> int:
    print(f"\n{'='*60}\nRunning {script}\n{'='*60}")
    result = subprocess.run([sys.executable, str(SCRIPTS / script)], check=False)
    return result.returncode

if __name__ == "__main__":
    rc1 = run("load_strava.py")
    rc2 = run("dedupe_cycling.py")
    rc3 = run("enrich_cycling_hr.py")
    if any(rc != 0 for rc in (rc1, rc2, rc3)):
        print(f"\nWARNING: One or more scripts had non-zero exit: {rc1=}, {rc2=}, {rc3=}")
        sys.exit(1)
    print("\nAll daily sync steps completed successfully.")
