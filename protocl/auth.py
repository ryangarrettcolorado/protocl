"""v3.2 Beta Tier — Google SSO auth, allowlist + role assignment, page guard.

Authentication uses Streamlit's native OIDC integration (``st.login`` /
``st.user`` / ``st.logout``), available in Streamlit >= 1.42. The Google OIDC
provider is configured under ``[auth]`` in ``.streamlit/secrets.toml`` (see
``secrets.toml.example``).

The pure logic — allowlist matching, email slugification, role resolution — is
kept free of Streamlit calls so it can be unit-tested with the lightweight
shim in ``tests/conftest.py``. The Streamlit-touching pieces (``require_auth``,
the login/denial UI) live below the pure helpers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import streamlit as st


ROLE_OWNER = "owner"
ROLE_BETA = "beta_user"

# The owner reuses the existing single-tenant data directory (data/ryan) so the
# v3.2 migration never has to move Ryan's real data. Beta users get fresh dirs
# under data/profiles/<slug>/ (see storage.ProfileStorage).
OWNER_PROFILE_ID = "ryan"

ALLOWLIST_PATH = Path(__file__).resolve().parent.parent / "config" / "allowlist.yaml"


# ────────────────────────────────────────────────────────────────────────────
# Allowlist loading (pure)
# ────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Principal:
    """A resolved, authorized user."""
    email: str
    role: str
    profile_id: str
    display_name: str


def _slugify_email(email: str) -> str:
    """Turn an email into a filesystem-safe profile id.

    ``friend@gmail.com`` -> ``friend_at_gmail_com``. Lowercased; any run of
    non-alphanumeric characters collapses to a single underscore.
    """
    local = email.strip().lower().replace("@", "_at_")
    slug = re.sub(r"[^a-z0-9]+", "_", local).strip("_")
    return slug or "user"


@lru_cache(maxsize=1)
def _load_allowlist_raw(path_str: str) -> dict[str, Any]:
    import yaml  # local import so the module imports even if PyYAML is absent

    with open(path_str) as f:
        data = yaml.safe_load(f) or {}
    return data


def load_allowlist(path: Path | str | None = None) -> dict[str, Any]:
    """Read allowlist.yaml. Cached by path string."""
    p = str(path or ALLOWLIST_PATH)
    return _load_allowlist_raw(p)


def resolve_principal(email: str | None, allowlist: dict[str, Any] | None = None) -> Principal | None:
    """Resolve an email to a :class:`Principal`, or ``None`` if not allowed.

    Matching is case-insensitive and whitespace-insensitive. The owner takes
    precedence over a (mistaken) duplicate entry in ``beta_users``.
    """
    if not email:
        return None
    allow = allowlist if allowlist is not None else load_allowlist()
    target = email.strip().lower()

    owner = (allow.get("owner") or {})
    owner_email = (owner.get("email") or "").strip().lower()
    if owner_email and target == owner_email:
        return Principal(
            email=target,
            role=ROLE_OWNER,
            profile_id=OWNER_PROFILE_ID,
            display_name=owner.get("name") or "Owner",
        )

    for entry in (allow.get("beta_users") or []):
        entry_email = (entry.get("email") or "").strip().lower()
        if entry_email and target == entry_email:
            return Principal(
                email=target,
                role=ROLE_BETA,
                profile_id=_slugify_email(target),
                display_name=entry.get("display_name") or entry_email.split("@")[0],
            )
    return None


def is_allowed(email: str | None, allowlist: dict[str, Any] | None = None) -> bool:
    return resolve_principal(email, allowlist) is not None


# ────────────────────────────────────────────────────────────────────────────
# Session helpers
# ────────────────────────────────────────────────────────────────────────────

def current_role() -> str | None:
    return st.session_state.get("role")


def is_owner() -> bool:
    return current_role() == ROLE_OWNER


def current_profile_id() -> str | None:
    """The profile currently being viewed (may be an impersonated user)."""
    return st.session_state.get("profile_id")


def is_read_only() -> bool:
    """True when the owner is impersonating a beta user (read-only mode)."""
    return bool(st.session_state.get("read_only"))


def _logged_in_email() -> str | None:
    """Best-effort read of the authenticated email from st.user."""
    user = getattr(st, "user", None)
    if user is None:
        return None
    # st.user behaves like a mapping; email may be absent before login.
    try:
        return user.get("email") if hasattr(user, "get") else getattr(user, "email", None)
    except Exception:
        return None


def _is_logged_in() -> bool:
    user = getattr(st, "user", None)
    if user is None:
        return False
    try:
        val = user.get("is_logged_in") if hasattr(user, "get") else getattr(user, "is_logged_in", False)
    except Exception:
        val = False
    return bool(val)


# ────────────────────────────────────────────────────────────────────────────
# UI: login / denial / guard
# ────────────────────────────────────────────────────────────────────────────

def _render_login() -> None:
    st.title("⚗️ Protocōl")
    st.subheader("Health Intelligence OS — Private Beta")
    st.write(
        "This is a personal, invite-only beta. Sign in with the Google account "
        "Ryan added to the beta list."
    )
    st.button("Sign in with Google", type="primary", on_click=st.login)
    st.caption("By signing in you agree to the privacy notice linked in the footer.")


def _render_denial(email: str | None) -> None:
    import audit

    st.title("⚗️ Protocōl")
    st.error("You're not on the beta list. Contact Ryan to request access.")
    if email:
        st.caption(f"Signed in as {email} — this address isn't authorized.")
    audit.log("denial", details=f"email={email or 'unknown'}")
    st.button("Sign out", on_click=st.logout)
    st.stop()


def require_auth() -> Principal:
    """Guard placed at the top of every page.

    Renders the login button (and stops) if the visitor is not authenticated;
    renders a denial page (and stops) if their email is not on the allowlist;
    otherwise establishes ``st.session_state`` role/profile_id and returns the
    resolved :class:`Principal`.
    """
    import audit

    if not _is_logged_in():
        _render_login()
        st.stop()

    email = _logged_in_email()
    principal = resolve_principal(email)
    if principal is None:
        _render_denial(email)
        # _render_denial calls st.stop(); the return below is unreachable in
        # the real app but keeps type-checkers happy.
        raise RuntimeError("unauthorized")

    # First time we see this session, record the base identity + login event.
    if st.session_state.get("auth_email") != principal.email:
        st.session_state["auth_email"] = principal.email
        st.session_state["base_role"] = principal.role
        st.session_state["base_profile_id"] = principal.profile_id
        st.session_state["base_display_name"] = principal.display_name
        audit.log("login", profile_id=principal.profile_id,
                  details=f"role={principal.role}")

    # Default the active profile to the user's own unless impersonating.
    if "profile_id" not in st.session_state or not st.session_state.get("impersonating"):
        st.session_state.setdefault("role", principal.role)
        if not st.session_state.get("impersonating"):
            st.session_state["role"] = principal.role
            st.session_state["profile_id"] = principal.profile_id
            st.session_state["display_name"] = principal.display_name
            st.session_state["read_only"] = False

    return principal


def logout_button() -> None:
    """Sidebar logout control; logs the event."""
    import audit

    if st.sidebar.button("Sign out"):
        audit.log("logout", profile_id=current_profile_id() or "unknown")
        st.logout()


# ────────────────────────────────────────────────────────────────────────────
# Owner impersonation (read-only)
# ────────────────────────────────────────────────────────────────────────────

def start_impersonation(profile_id: str, display_name: str) -> None:
    """Owner-only: temporarily view another user's data, read-only."""
    import audit

    if not is_owner():
        return
    st.session_state["impersonating"] = True
    st.session_state["profile_id"] = profile_id
    st.session_state["display_name"] = display_name
    st.session_state["read_only"] = True
    audit.log("impersonation_start", profile_id=profile_id,
              details=f"by={st.session_state.get('auth_email')}")


def stop_impersonation() -> None:
    import audit

    target = current_profile_id()
    st.session_state["impersonating"] = False
    st.session_state["read_only"] = False
    st.session_state["profile_id"] = st.session_state.get("base_profile_id", OWNER_PROFILE_ID)
    st.session_state["role"] = st.session_state.get("base_role", ROLE_OWNER)
    st.session_state["display_name"] = st.session_state.get("base_display_name", "Owner")
    audit.log("impersonation_end", profile_id=target or "unknown")


def render_impersonation_banner() -> None:
    """Top-of-page banner shown while the owner is impersonating a user."""
    if st.session_state.get("impersonating"):
        name = st.session_state.get("display_name", "user")
        c1, c2 = st.columns([5, 1])
        with c1:
            st.warning(f"🔍 Viewing {name}'s data (read-only).")
        with c2:
            if st.button("Exit view"):
                stop_impersonation()
                st.rerun()
