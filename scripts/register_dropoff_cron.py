"""Register the daily drop-off-detector cron via Perplexity Computer's pplx-tool.

USAGE — Ryan should run this manually. DO NOT register the cron from within an
autonomous build; cron jobs persist across sessions. This script is committed
for reproducibility — invoking it is a one-time human action.

Schedule: 8:00 AM MT daily.
  - 14:00 UTC = 8:00 AM MDT (summer, UTC-6)
  - 15:00 UTC = 8:00 AM MST (winter, UTC-7)
We register at 15:00 UTC (`0 15 * * *`); in summer it lands at 9:00 AM local,
acceptable for a once-daily re-engagement scan.
"""
from __future__ import annotations

import textwrap


CRON_EXPR = "0 15 * * *"  # 8:00 AM MST / 9:00 AM MDT
JOB_NAME = "protocl-dropoff-detector"
COMMAND = "cd /path/to/protocl && python scripts/dropoff_detector.py"


def main() -> None:
    print(textwrap.dedent(f"""
        To register the daily drop-off detector cron, run this in Perplexity Computer:

            pplx-tool schedule_cron \\
                --name "{JOB_NAME}" \\
                --cron "{CRON_EXPR}" \\
                --command "{COMMAND}"

        Stages: 7d in-app nudge · 14d owner notify · 30d auto-pause sync.
    """).strip())


if __name__ == "__main__":
    main()
