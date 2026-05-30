"""v3.5 — daily error digest.

Reads the last 24h of ``data/shared/error_log.csv``, groups by traceback hash,
and (if any errors) notifies the owner via the in-app owner inbox + a
best-effort email. Zero errors → no notification.

Run by a registered cron at 7:00 AM MT (see ``register_error_digest_cron.py``).
This script is safe to invoke manually for testing.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCL = REPO_ROOT / "protocl"
sys.path.insert(0, str(PROTOCL))


def build_digest_text() -> tuple[int, str]:
    """Return (total_error_count, markdown_digest). Empty digest if no errors."""
    from modules import error_capture

    grouped = error_capture.group_by_hash(since_hours=24)
    if grouped.empty:
        return 0, ""
    total = int(grouped["count"].sum())
    lines = [f"# Protocōl error digest — {total} error(s) in 24h", ""]
    for _, r in grouped.iterrows():
        lines.append(
            f"- **{r['exception_type']}** ×{int(r['count'])} "
            f"(`{r['traceback_hash']}`) — {r['message']}"
        )
    return total, "\n".join(lines)


def run_digest() -> dict[str, object]:
    """Compose + dispatch the digest. Returns a small report dict."""
    import owner_inbox
    from auth import load_allowlist

    total, md = build_digest_text()
    if total == 0:
        print("No errors in the last 24h — skipping digest.")
        return {"errors": 0, "notified": False}

    owner_inbox.add(md.splitlines()[0], kind="error_digest")

    notified_email = False
    try:
        from modules import notifications
        owner_email = (load_allowlist().get("owner") or {}).get("email")
        if owner_email and notifications.is_configured():
            html = notifications._md_to_html(md)
            notified_email = notifications.send_email(
                owner_email, "Protocōl — daily error digest", html, md
            )
    except Exception as exc:
        print(f"Email digest failed (non-fatal): {exc}")

    print(md)
    return {"errors": total, "notified": True, "email_sent": notified_email}


if __name__ == "__main__":
    run_digest()
