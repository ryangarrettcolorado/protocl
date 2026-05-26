"""Live-API ingest scaffolds.

Each submodule implements a single `pull(start_date, end_date) -> pd.DataFrame`
that returns rows in the schema of one of the target CSVs. The Import Center
calls these on demand; nightly cron will eventually drive them automatically.

All modules degrade gracefully when their secret is missing.
"""
from __future__ import annotations
