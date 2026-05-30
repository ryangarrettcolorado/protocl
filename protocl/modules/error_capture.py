"""v3.5 — lightweight in-app error capture + daily digest source.

No external Sentry dependency. ``capture_error`` writes a structured row to
``data/shared/error_log.csv`` and deduplicates identical errors by a stable
``traceback_hash``: a repeat of the same traceback is only logged again when
more than :data:`DEDUP_WINDOW_HOURS` has elapsed since the last identical row.

The shell wraps page execution; on an unhandled exception it captures the error
and renders a friendly "Something went wrong" page with a "Send context to
Ryan" button (which files a feedback entry carrying the error context).
"""
from __future__ import annotations

import hashlib
import traceback as tb_mod
from datetime import datetime, timedelta, timezone

import pandas as pd

import storage


ERROR_LOG = "error_log.csv"
COLUMNS = ["timestamp", "profile_id", "page", "exception_type", "message",
           "traceback_hash", "user_facing_message"]
DEDUP_WINDOW_HOURS = 1
USER_FACING_MESSAGE = "Something went wrong. We've been notified."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def traceback_hash(exc: BaseException) -> str:
    """Stable hash of an exception's traceback (frames + type), independent of
    timestamps or memory addresses, so identical errors collapse together."""
    frames = tb_mod.extract_tb(exc.__traceback__)
    sig_parts = [type(exc).__name__]
    for fr in frames:
        sig_parts.append(f"{fr.filename}:{fr.lineno}:{fr.name}")
    sig = "\n".join(sig_parts)
    return hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]


def _recent_identical(th: str, now: datetime) -> bool:
    path = storage.SHARED_DIR / ERROR_LOG
    if not path.exists():
        return False
    df = pd.read_csv(path)
    if df.empty or "traceback_hash" not in df.columns:
        return False
    same = df[df["traceback_hash"] == th]
    if same.empty:
        return False
    ts = pd.to_datetime(same["timestamp"], errors="coerce", utc=True).dropna()
    if ts.empty:
        return False
    last = ts.max().to_pydatetime()
    return (now - last) < timedelta(hours=DEDUP_WINDOW_HOURS)


def capture_error(exc: BaseException, *, page: str = "", profile_id: str = "",
                  now: datetime | None = None) -> str:
    """Log a structured error row (deduplicated). Returns the traceback hash."""
    now = now or _now()
    th = traceback_hash(exc)
    try:
        if _recent_identical(th, now):
            return th
        storage.append_shared_csv(
            ERROR_LOG,
            {
                "timestamp": now.isoformat(timespec="seconds"),
                "profile_id": profile_id,
                "page": page,
                "exception_type": type(exc).__name__,
                "message": str(exc)[:500],
                "traceback_hash": th,
                "user_facing_message": USER_FACING_MESSAGE,
            },
            COLUMNS,
        )
    except Exception:
        pass
    return th


def read_errors() -> pd.DataFrame:
    return storage.read_shared_csv(ERROR_LOG, parse_dates=["timestamp"])


def group_by_hash(since_hours: int = 24, now: datetime | None = None) -> pd.DataFrame:
    """Group the last ``since_hours`` of errors by traceback_hash with counts.

    Returns columns: ``traceback_hash, exception_type, message, count, last_seen``.
    """
    df = read_errors()
    if df.empty:
        return pd.DataFrame(columns=["traceback_hash", "exception_type", "message", "count", "last_seen"])
    now = now or _now()
    ts = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    cutoff = pd.Timestamp(now - timedelta(hours=since_hours))
    df = df[ts >= cutoff]
    if df.empty:
        return pd.DataFrame(columns=["traceback_hash", "exception_type", "message", "count", "last_seen"])
    grouped = (
        df.groupby("traceback_hash")
        .agg(
            exception_type=("exception_type", "first"),
            message=("message", "first"),
            count=("traceback_hash", "size"),
            last_seen=("timestamp", "max"),
        )
        .reset_index()
        .sort_values("count", ascending=False)
    )
    return grouped


# ── "Mark as fixed" toggle state (owner admin) ──────────────────────────────

FIXED_FILE = "error_fixed.csv"
FIXED_COLUMNS = ["traceback_hash", "fixed_at"]


def mark_fixed(traceback_hash_value: str) -> None:
    storage.append_shared_csv(
        FIXED_FILE,
        {"traceback_hash": traceback_hash_value, "fixed_at": _now().isoformat(timespec="seconds")},
        FIXED_COLUMNS,
    )


def fixed_hashes() -> set[str]:
    df = storage.read_shared_csv(FIXED_FILE)
    if df.empty or "traceback_hash" not in df.columns:
        return set()
    return set(df["traceback_hash"].astype(str).tolist())
