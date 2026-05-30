"""
daily_sync.py — Combined Strava (+ optional Apple Health HR) daily refresh.

Designed to be invoked by the cron job. Runs:
  1. load_strava.py        — pull Strava activities, dedupe vs HK/GPX, update training.csv
  2. dedupe_cycling.py     — merge same-day HK+Strava cycling duplicates
  3. enrich_cycling_hr.py  — backfill HR for cycling rows missing it (skipped
                              automatically when the HR raw file isn't present
                              or when SKIP_HR_ENRICH=1 is set)

The HR step is skipped by the background cron because the Apple Health
connector is device-attached and only reachable in interactive sessions.
To run HR enrichment on-demand, fetch fresh _hr_raw.json in an interactive
session and run `python3 scripts/enrich_cycling_hr.py` directly.

Assumes:
  - data/ryan/_strava_raw.json has been populated before this runs
  - data/ryan/_hr_raw.json optional; if missing the HR step is auto-skipped
    (set HR_RAW env var to override the default path)
"""
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent  # protocl/protocl
DEFAULT_HR_RAW = REPO_ROOT / "data" / "ryan" / "_hr_raw.json"


def run(script: str) -> int:
    print(f"\n{'='*60}\nRunning {script}\n{'='*60}")
    result = subprocess.run([sys.executable, str(SCRIPTS / script)], check=False)
    return result.returncode


def should_skip_hr() -> tuple[bool, str]:
    """Return (skip, reason) for the HR enrichment step."""
    if os.environ.get("SKIP_HR_ENRICH") == "1":
        return True, "SKIP_HR_ENRICH=1 set in environment"
    hr_path = Path(os.environ.get("HR_RAW", DEFAULT_HR_RAW))
    if not hr_path.exists():
        return True, f"HR raw file not found at {hr_path}"
    return False, ""


def run_orchestrated_sync() -> None:
    """v3.5 — fan the daily sync out across every opted-in beta user.

    Iterates the allowlist, honours each user's per-source ``auto_sync`` opt-in,
    isolates per-source failures, enforces the daily run cap, and logs to
    ``data/shared/sync_log.csv``. Import is local so the owner-only Strava flow
    above still works even if Streamlit/app deps are unavailable.
    """
    sys.path.insert(0, str(REPO_ROOT))
    from modules.sync_orchestrator import run_daily_sync_for_all_profiles

    print(f"\n{'='*60}\nOrchestrated per-user sync\n{'='*60}")
    report = run_daily_sync_for_all_profiles()
    print(
        f"Sync runs: {report.runs_used} · ok: {report.ok_count} · "
        f"errors: {report.error_count} · budget_reached: {report.budget_reached}"
    )


if __name__ == "__main__":
    rc1 = run("load_strava.py")
    rc2 = run("dedupe_cycling.py")

    skip, reason = should_skip_hr()
    if skip:
        print(f"\n{'='*60}\nSkipping enrich_cycling_hr.py: {reason}\n{'='*60}")
        rc3 = 0
    else:
        rc3 = run("enrich_cycling_hr.py")

    # v3.5 — fan out to all opted-in beta users (error-isolated, capped).
    try:
        run_orchestrated_sync()
    except Exception as exc:  # never let the fan-out break the owner's sync
        print(f"WARNING: orchestrated sync failed: {exc}")

    if any(rc != 0 for rc in (rc1, rc2, rc3)):
        print(f"\nWARNING: One or more scripts had non-zero exit: {rc1=}, {rc2=}, {rc3=}")
        sys.exit(1)
    print("\nAll daily sync steps completed successfully.")
