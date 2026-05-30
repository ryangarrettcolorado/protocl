"""v3.2 — allowlist matching, email slugification, role resolution (pure logic)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import auth


ALLOWLIST = {
    "owner": {"email": "ryangarrettcolorado@gmail.com", "name": "Ryan Garrett"},
    "beta_users": [
        {"email": "friend@gmail.com", "display_name": "Friend"},
        {"email": "Second.User@Example.com"},
    ],
}


def test_owner_resolves_to_owner_role_and_legacy_dir():
    p = auth.resolve_principal("ryangarrettcolorado@gmail.com", ALLOWLIST)
    assert p is not None
    assert p.role == auth.ROLE_OWNER
    assert p.profile_id == auth.OWNER_PROFILE_ID == "ryan"
    assert p.display_name == "Ryan Garrett"


def test_owner_match_is_case_insensitive():
    p = auth.resolve_principal("  RyanGarrettColorado@GMAIL.com ", ALLOWLIST)
    assert p is not None and p.role == auth.ROLE_OWNER


def test_beta_user_resolves_with_slugified_profile_id():
    p = auth.resolve_principal("friend@gmail.com", ALLOWLIST)
    assert p is not None
    assert p.role == auth.ROLE_BETA
    assert p.profile_id == "friend_at_gmail_com"
    assert p.display_name == "Friend"


def test_beta_display_name_defaults_to_local_part():
    p = auth.resolve_principal("second.user@example.com", ALLOWLIST)
    assert p is not None
    assert p.display_name == "second.user"


def test_unknown_email_is_denied():
    assert auth.resolve_principal("stranger@nowhere.com", ALLOWLIST) is None
    assert auth.is_allowed("stranger@nowhere.com", ALLOWLIST) is False


def test_none_or_empty_email_denied():
    assert auth.resolve_principal(None, ALLOWLIST) is None
    assert auth.resolve_principal("", ALLOWLIST) is None


def test_slugify_email_examples():
    assert auth._slugify_email("a.b+c@gmail.com") == "a_b_c_at_gmail_com"
    # All-symbol input still collapses to a safe non-empty slug.
    assert auth._slugify_email("***") == "user"


def test_owner_takes_precedence_over_duplicate_beta_entry():
    al = {
        "owner": {"email": "dup@x.com", "name": "Owner"},
        "beta_users": [{"email": "dup@x.com"}],
    }
    p = auth.resolve_principal("dup@x.com", al)
    assert p.role == auth.ROLE_OWNER


def test_shipped_allowlist_has_owner_and_five_beta_slots():
    al = auth.load_allowlist()
    assert (al.get("owner") or {}).get("email") == "ryangarrettcolorado@gmail.com"
    assert len(al.get("beta_users") or []) == 5
