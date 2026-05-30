"""v3.2 — append-only audit log.

Every security-relevant event (login, logout, denial, consent changes,
impersonation, exports, settings changes, LLM budget events) is appended to
``data/shared/audit_log.csv``. IPs are never stored raw — only a one-way
SHA-256 hash, so the log can prove "same visitor" without being PII.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import storage


AUDIT_FILE = "audit_log.csv"
COLUMNS = ["timestamp", "profile_id", "action", "details", "ip_hash"]

# Actions enumerated in spec 1.6.
ACTIONS = {
    "login", "logout", "denial", "consent_granted", "consent_revoked",
    "impersonation_start", "impersonation_end", "data_export", "settings_change",
    "llm_budget_reached",
    # v3.5 account deletion
    "account_delete_initiated", "account_delete_confirmed",
    "account_restore_from_soft_delete",
    # v3.6 drop-off detector
    "dropoff_nudge_sent", "dropoff_owner_notified", "dropoff_sync_paused",
}


def hash_ip(ip: str | None) -> str:
    """One-way SHA-256 of an IP. Empty string for unknown IPs."""
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(action: str, *, profile_id: str | None = None, details: str = "",
        ip: str | None = None) -> None:
    """Append an audit event. Best-effort: never raises into page code."""
    try:
        storage.append_shared_csv(
            AUDIT_FILE,
            {
                "timestamp": _now(),
                "profile_id": profile_id or "",
                "action": action,
                "details": details,
                "ip_hash": hash_ip(ip),
            },
            COLUMNS,
        )
    except Exception:
        # Auditing must not take down the app.
        pass


def read_log():
    return storage.read_shared_csv(AUDIT_FILE, parse_dates=["timestamp"])


def last_login(profile_id: str):
    """Timestamp of a profile's most recent ``login`` audit row, or None.

    Sourced from the shared audit log so it works for every beta user
    regardless of their analytics-tracking opt-in (used by the drop-off
    detector, spec 2.4).
    """
    import pandas as pd

    df = read_log()
    if df.empty or "action" not in df.columns or "profile_id" not in df.columns:
        return None
    rows = df[(df["profile_id"] == profile_id) & (df["action"] == "login")]
    ts = pd.to_datetime(rows.get("timestamp"), errors="coerce").dropna() if not rows.empty else pd.Series([], dtype="datetime64[ns]")
    if ts.empty:
        return None
    out = ts.max().to_pydatetime()
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)
