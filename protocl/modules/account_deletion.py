"""v3.5 — self-serve account deletion (privacy promise).

The deletion flow is pure-logic-first so it can be unit-tested without
Streamlit:

1. **Soft-delete** the live profile directory into
   ``data/deleted/<profile_id>_<timestamp>.zip`` (90-day retention for
   accidental-deletion recovery), then remove the live directory.
2. **Scrub PII** from every shared log: rows whose ``profile_id`` matches the
   deleted user have that field replaced with ``deleted_<hash8>`` — the
   timestamp + action are *kept* for the security audit trail (we never delete
   shared rows). ``display_name`` is blanked.
3. **Audit** ``account_delete_initiated`` / ``account_delete_confirmed``.
4. **Notify** the owner (in-app + best-effort email).

The owner can never delete their own account from the UI (it would brick the
app); :func:`can_delete` returns ``False`` for the owner profile.
"""
from __future__ import annotations

import hashlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

import audit
import storage
from storage import ProfileStorage


OWNER_PROFILE_ID = "ryan"
SOFT_DELETE_RETENTION_DAYS = 90

# Shared logs that may carry a profile_id we must scrub on deletion.
SHARED_LOGS_TO_SCRUB = (
    "all_feedback.csv",
    "audit_log.csv",
    "llm_cost_log.csv",
    "sync_log.csv",
    "sync_errors.csv",
    "nps_responses.csv",
    "error_log.csv",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash8(profile_id: str) -> str:
    return hashlib.sha256(profile_id.encode("utf-8")).hexdigest()[:8]


def deleted_dir() -> Path:
    d = storage.DATA_DIR / "deleted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def can_delete(profile_id: str) -> bool:
    """Owner accounts cannot be self-deleted from the UI."""
    return profile_id != OWNER_PROFILE_ID


# ────────────────────────────────────────────────────────────────────────────
# Soft-delete (zip + remove)
# ────────────────────────────────────────────────────────────────────────────

def soft_delete_profile(store: ProfileStorage) -> Path | None:
    """Zip the profile dir into ``data/deleted/`` then remove the live dir.

    Returns the zip path (or ``None`` if the profile dir didn't exist).
    """
    src = store.profile_dir
    if not src.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    zip_path = deleted_dir() / f"{store.profile_id}_{ts}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(src))
    # Remove the live directory after a successful archive.
    for f in sorted(src.rglob("*"), reverse=True):
        if f.is_file():
            f.unlink()
    for d in sorted([p for p in src.rglob("*") if p.is_dir()], reverse=True):
        d.rmdir()
    src.rmdir()
    return zip_path


# ────────────────────────────────────────────────────────────────────────────
# Shared-log PII scrub
# ────────────────────────────────────────────────────────────────────────────

def scrub_shared_logs(profile_id: str, logs: tuple[str, ...] = SHARED_LOGS_TO_SCRUB) -> dict[str, int]:
    """Replace ``profile_id`` with ``deleted_<hash8>`` (and blank display_name)
    in every shared log. Rows are never removed — timestamp + action stay for
    the audit trail. Returns ``{filename: rows_scrubbed}``.
    """
    replacement = f"deleted_{_hash8(profile_id)}"
    scrubbed: dict[str, int] = {}
    for name in logs:
        path = storage.SHARED_DIR / name
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if df.empty or "profile_id" not in df.columns:
            continue
        mask = df["profile_id"].astype(str) == profile_id
        count = int(mask.sum())
        if count:
            df.loc[mask, "profile_id"] = replacement
            if "display_name" in df.columns:
                df.loc[mask, "display_name"] = ""
            df.to_csv(path, index=False)
        scrubbed[name] = count
    return scrubbed


# ────────────────────────────────────────────────────────────────────────────
# Owner notification
# ────────────────────────────────────────────────────────────────────────────

def notify_owner_of_deletion(display_name: str, owner_email: str | None = None) -> None:
    """Best-effort owner notification: in-app queue + email if configured."""
    ts = _now_iso()
    msg = f"Beta user {display_name} deleted their account at {ts}."
    try:
        import owner_inbox
        owner_inbox.add(msg, kind="account_deletion")
    except Exception:
        pass
    if owner_email:
        try:
            from modules import notifications
            if notifications.is_configured():
                html = notifications._md_to_html(f"## Account deletion\n\n{msg}")
                notifications.send_email(owner_email, "Protocōl — account deleted", html, msg)
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────────────

def delete_account(store: ProfileStorage, display_name: str = "",
                   owner_email: str | None = None) -> dict[str, object]:
    """Full deletion: audit → scrub → soft-delete → notify owner.

    Refuses to delete the owner profile. Returns a small report dict.
    """
    pid = store.profile_id
    if not can_delete(pid):
        raise ValueError("Owner accounts cannot be deleted from the UI.")

    audit.log("account_delete_initiated", profile_id=pid)
    scrubbed = scrub_shared_logs(pid)
    zip_path = soft_delete_profile(store)
    # Audit AFTER scrub so this confirmation row is the one entry that still
    # names the (now-deleted) profile, proving the deletion happened.
    audit.log("account_delete_confirmed", profile_id=pid,
              details=f"zip={zip_path.name if zip_path else 'none'}")
    notify_owner_of_deletion(display_name or pid, owner_email)
    return {
        "profile_id": pid,
        "zip_path": str(zip_path) if zip_path else None,
        "scrubbed": scrubbed,
    }


# ────────────────────────────────────────────────────────────────────────────
# Admin restore (owner-only)
# ────────────────────────────────────────────────────────────────────────────

def list_soft_deleted() -> list[dict[str, str]]:
    """List the soft-delete archives in ``data/deleted/`` (owner admin)."""
    d = storage.DATA_DIR / "deleted"
    if not d.exists():
        return []
    out = []
    for f in sorted(d.glob("*.zip"), reverse=True):
        stem = f.stem  # <profile_id>_<YYYYmmdd>_<HHMMSS>
        parts = stem.rsplit("_", 2)
        pid = parts[0] if len(parts) == 3 else stem
        out.append({
            "zip": f.name,
            "profile_id": pid,
            "deleted_at": "_".join(parts[1:]) if len(parts) == 3 else "",
            "size_kb": f"{f.stat().st_size / 1024:.1f}",
        })
    return out


def restore_from_soft_delete(zip_name: str) -> str:
    """Restore a soft-deleted profile from its archive (owner-only)."""
    src = storage.DATA_DIR / "deleted" / zip_name
    if not src.exists():
        raise FileNotFoundError(zip_name)
    stem = src.stem
    parts = stem.rsplit("_", 2)
    pid = parts[0] if len(parts) == 3 else stem
    dest = storage.PROFILES_DIR / pid
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zf:
        zf.extractall(dest)
    audit.log("account_restore_from_soft_delete", profile_id=pid,
              details=f"zip={zip_name}")
    return pid
