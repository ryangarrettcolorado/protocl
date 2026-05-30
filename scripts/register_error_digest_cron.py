"""Register the daily error-digest cron via Perplexity Computer's pplx-tool.

USAGE — Ryan should run this manually. DO NOT register the cron from within an
autonomous build; cron jobs persist across sessions. This script is committed
for reproducibility — invoking it is a one-time human action.

Schedule: 7:00 AM MT daily.
  - 13:00 UTC = 7:00 AM MDT (summer, UTC-6)
  - 14:00 UTC = 7:00 AM MST (winter, UTC-7)
We register at 14:00 UTC (`0 14 * * *`); in summer the digest lands at 8:00 AM
local, which is acceptable for a once-daily digest.
"""
from __future__ import annotations

import textwrap


CRON_EXPR = "0 14 * * *"  # 7:00 AM MST / 8:00 AM MDT
JOB_NAME = "protocl-error-digest"
COMMAND = "cd /path/to/protocl && python scripts/error_digest.py"


def main() -> None:
    print(textwrap.dedent(f"""
        To register the daily error-digest cron, run this in Perplexity Computer:

            pplx-tool schedule_cron \\
                --name "{JOB_NAME}" \\
                --cron "{CRON_EXPR}" \\
                --command "{COMMAND}"

        The digest only notifies the owner on days with at least one error.
    """).strip())


if __name__ == "__main__":
    main()
