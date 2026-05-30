"""Admin · Beta Overview (owner-only) — spec 1.4.

Lists beta users with signup date, last active, consent status, feedback count,
and an "Impersonate (read-only)" button (enabled only for consenting users).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import consent as consent_mod
import feedback as feedback_mod
from auth import load_allowlist
from explainers import cache as explainer_cache
from storage import PROFILES_DIR, ProfileStorage

auth.require_auth()
if not auth.is_owner():
    st.error("This page is owner-only.")
    st.stop()

st.title("👥 Beta Overview")
st.caption("Manage beta users, view consent status, and impersonate (read-only) consenting users.")

allow = load_allowlist()
audit_df = __import__("audit").read_log()


def _last_active(profile_id: str) -> str:
    if audit_df.empty:
        return "—"
    rows = audit_df[audit_df["profile_id"] == profile_id]
    if rows.empty:
        return "—"
    return str(rows["timestamp"].max())


rows = []
for entry in allow.get("beta_users", []):
    email = (entry.get("email") or "").lower()
    if not email or email.endswith("@example.com"):
        continue  # skip unfilled placeholder slots
    pid = auth._slugify_email(email)
    store = ProfileStorage()
    store.profile_id = pid  # read-only inspection of consent file
    c = consent_mod.load_consent(store)
    rows.append({
        "profile_id": pid,
        "display_name": entry.get("display_name", email.split("@")[0]),
        "email": email,
        "signup": c.get("privacy_accepted_at") or "—",
        "last_active": _last_active(pid),
        "owner_visibility": consent_mod.owner_can_view(store),
        "feedback": feedback_mod.feedback_count(pid),
    })

if not rows:
    st.info("No active beta users yet. Add real emails to `config/allowlist.yaml` and redeploy.")
    st.stop()

for r in rows:
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            st.markdown(f"**{r['display_name']}**  \n`{r['email']}`")
            st.caption(f"Signup: {r['signup']} · Last active: {r['last_active']}")
        with c2:
            st.metric("Feedback", r["feedback"])
            st.caption("Owner visibility: " + ("✅ consented" if r["owner_visibility"] else "🚫 not consented"))
        with c3:
            can = r["owner_visibility"]
            if st.button("Impersonate (read-only)", key=f"imp_{r['profile_id']}", disabled=not can):
                auth.start_impersonation(r["profile_id"], r["display_name"])
                st.rerun()
            if st.button("Clear explainer cache", key=f"clr_{r['profile_id']}"):
                s = ProfileStorage()
                s.profile_id = r["profile_id"]
                explainer_cache.clear_user(s)
                st.success("Cleared.")


# ── Soft-deleted accounts (v3.5) ────────────────────────────────────────────
from modules import account_deletion as _acct_del  # noqa: E402

st.divider()
st.subheader("🗑 Soft-deleted accounts")
st.caption("Archives retained for 90 days for accidental-deletion recovery.")
_archives = _acct_del.list_soft_deleted()
if not _archives:
    st.caption("No soft-deleted accounts.")
else:
    for a in _archives:
        ac1, ac2 = st.columns([4, 1])
        with ac1:
            st.markdown(f"**{a['profile_id']}** · deleted {a['deleted_at']} · {a['size_kb']} KB")
            st.caption(a["zip"])
        with ac2:
            if st.button("Restore", key=f"restore_{a['zip']}"):
                pid = _acct_del.restore_from_soft_delete(a["zip"])
                st.success(f"Restored {pid}.")
                st.rerun()


# ── Sync health (v3.5) ──────────────────────────────────────────────────────
from modules import sync_orchestrator as _sync  # noqa: E402

st.divider()
st.subheader("🔄 Sync health")
_last_sync = _sync.last_sync_per_profile()
_errors_df = _sync.read_sync_errors()
if not _last_sync and _errors_df.empty:
    st.caption("No sync runs recorded yet.")
else:
    _rows = []
    for _pid, _ts in sorted(_last_sync.items()):
        _ec = 0
        if not _errors_df.empty and "profile_id" in _errors_df.columns:
            _ec = int((_errors_df["profile_id"] == _pid).sum())
        _rows.append({"profile_id": _pid, "last_sync": _ts, "recent_errors": _ec})
    st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
