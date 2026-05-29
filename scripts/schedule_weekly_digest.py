"""Register the weekly digest cron job via Perplexity Computer's pplx-tool.

USAGE — Ryan should run this manually after reviewing the v3.1 PR.

DO NOT register the cron job from within an autonomous build. Cron jobs
persist across sessions and a misconfigured schedule would silently fire
incorrect digests until manually killed. This script is committed for
reproducibility — invoking it is a one-time human action.

The cron expression is `0 1 * * 1` (UTC), which corresponds to:
  - Sunday 18:00 MST  (winter, UTC-7)
  - Sunday 19:00 MDT  (summer, UTC-6)  — fires one hour later in DST

If you'd prefer the digest to always fire at exactly 18:00 local, register
TWO crons gated by month-of-year:
  Winter:  0 1 * * 1   (Nov–Mar)
  Summer:  0 0 * * 1   (Apr–Oct)
…and tear down/recreate at each DST transition. See DECISIONS.md for the
"first digest is a draft" safety mechanism this script depends on.

Invocation (inside Perplexity Computer):

    pplx-tool schedule_cron \\
        --name "protocl-weekly-digest" \\
        --cron "0 1 * * 1" \\
        --command "cd /path/to/protocl && python -c 'from modules.notifications import send_weekly_digest; print(send_weekly_digest())'"

After your inaugural digest lands as a draft in `protocl/data/ryan/drafts/`,
review it, then flip the gate by running:

    python -c "from modules.notifications import mark_first_digest_reviewed; mark_first_digest_reviewed()"

Subsequent digests will then send live.
"""
from __future__ import annotations

import textwrap


CRON_EXPR = "0 1 * * 1"  # Sunday 01:00 UTC = Sunday 18:00 MST (winter)
JOB_NAME = "protocl-weekly-digest"
COMMAND = (
    "cd /path/to/protocl && python -c "
    "'from modules.notifications import send_weekly_digest; "
    "print(send_weekly_digest())'"
)


def main() -> None:
    print(textwrap.dedent(f"""
        To register the weekly digest cron, run this in Perplexity Computer:

            pplx-tool schedule_cron \\
                --name "{JOB_NAME}" \\
                --cron "{CRON_EXPR}" \\
                --command "{COMMAND}"

        See module docstring for DST handling notes.
    """).strip())


if __name__ == "__main__":
    main()
