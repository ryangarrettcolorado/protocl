"""v3.6 — daily drop-off detector runner.

Thin wrapper around ``modules.dropoff.run``. Detection logic lives in the module
so it can be unit-tested without Streamlit. Safe to invoke manually for testing.

Registered by a daily cron at 8:00 AM MT (see ``register_dropoff_cron.py``).
Stages: 7d in-app nudge · 14d owner notify · 30d auto-pause sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCL = REPO_ROOT / "protocl"
sys.path.insert(0, str(PROTOCL))


def main() -> None:
    from modules import dropoff

    actions = dropoff.run()
    taken = [a for a in actions if a.action != "none"]
    print(f"Drop-off scan: {len(actions)} profile(s) evaluated, {len(taken)} action(s).")
    for a in taken:
        print(f"  - {a.profile_id}: {a.action} ({a.days_inactive:.0f}d inactive)")


if __name__ == "__main__":
    main()
