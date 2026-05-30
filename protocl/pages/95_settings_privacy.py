"""v3.5 — Settings · Privacy & Account deletion (self-serve)."""
from __future__ import annotations

import streamlit as st

import auth
from auth import load_allowlist
from modules import account_deletion, events
from modules.theme import inject_css
from storage import ProfileStorage

auth.require_auth()
inject_css()

store = ProfileStorage()
profile_id = store.profile_id
display_name = st.session_state.get("display_name", profile_id)

st.title("🔒 Privacy & Account")

# ── Post-deletion confirmation screen ───────────────────────────────────────
if st.session_state.get("_account_deleted"):
    st.success("Your data has been deleted.")
    st.write(
        "Your profile, uploaded data, feedback, and event logs have been removed. "
        "A 90-day recovery archive is retained in case this was accidental — "
        "contact Ryan to recover it before then."
    )
    if st.button("Return to landing page", type="primary"):
        st.logout()
    st.stop()

st.markdown(
    "Manage what happens to your data. To control owner visibility, use "
    "**Settings → Privacy & Consent**."
)

st.divider()
st.header("Delete your Protocōl account")
st.write(
    "This permanently removes your profile, all uploaded data, all feedback, "
    "and all event logs. We cannot recover this."
)
st.caption(
    "For accidental-deletion recovery, your data is soft-deleted to a private "
    "archive for 90 days before permanent removal. Security audit logs keep the "
    "deletion timestamp + action, but your profile id is replaced with an "
    "anonymized `deleted_<hash>` token — never your identity."
)

if not account_deletion.can_delete(profile_id):
    st.info(
        "Owner accounts must be deleted manually by the developer.",
        icon="🛡",
    )
    st.button("Permanently delete", type="primary", disabled=True)
    st.stop()

if st.session_state.get("read_only"):
    st.warning("Deletion is disabled while viewing another user's data (read-only).")
    st.stop()

# ── Two-step confirmation ────────────────────────────────────────────────────
typed = st.text_input(
    "Step 1 — type your email to confirm",
    key="_delete_email_confirm",
    placeholder=st.session_state.get("auth_email", "you@example.com"),
)
auth_email = (st.session_state.get("auth_email") or "").strip().lower()
email_ok = bool(auth_email) and typed.strip().lower() == auth_email

st.caption("Step 2 — this cannot be undone (90-day archive aside).")
if st.button("Permanently delete", type="primary", disabled=not email_ok):
    allow = load_allowlist()
    owner_email = (allow.get("owner") or {}).get("email")
    events.track("account_deleted", page="settings_privacy", store=store)
    account_deletion.delete_account(store, display_name=display_name, owner_email=owner_email)
    st.session_state["_account_deleted"] = True
    st.rerun()

if not email_ok and typed:
    st.caption("Email doesn't match the address you signed in with.")
