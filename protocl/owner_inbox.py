"""v3.5/v3.6 — owner in-app notification inbox.

A tiny append-only shared log (``data/shared/owner_inbox.csv``) that any module
or cron can drop an owner-facing notice into without needing email configured.
The owner reads it from the admin pages. This is app-level (not user-scoped),
so it always writes regardless of read-only impersonation state.

Schema: ``timestamp, kind, message, read``
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

import storage


INBOX_FILE = "owner_inbox.csv"
COLUMNS = ["timestamp", "kind", "message", "read"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def add(message: str, *, kind: str = "info") -> None:
    """Queue an owner notification. Best-effort; never raises into callers."""
    try:
        storage.append_shared_csv(
            INBOX_FILE,
            {"timestamp": _now(), "kind": kind, "message": message, "read": False},
            COLUMNS,
        )
    except Exception:
        pass


def read_inbox() -> pd.DataFrame:
    return storage.read_shared_csv(INBOX_FILE, parse_dates=["timestamp"])


def unread_count() -> int:
    df = read_inbox()
    if df.empty or "read" not in df.columns:
        return 0
    return int((~df["read"].astype(bool)).sum())


def mark_all_read() -> None:
    path = storage.shared_path(INBOX_FILE)
    if not path.exists():
        return
    df = pd.read_csv(path)
    if df.empty:
        return
    df["read"] = True
    df.to_csv(path, index=False)
