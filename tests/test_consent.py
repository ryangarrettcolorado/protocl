"""v3.2 — consent capture + owner-visibility (timestamped revocation)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st
import storage
import audit
import consent
from storage import ProfileStorage


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(storage, "SHARED_DIR", tmp_path / "shared")
    monkeypatch.setattr(storage, "OWNER_LEGACY_DIR", tmp_path / "ryan")
    monkeypatch.setattr(audit, "SHARED_DIR", tmp_path / "shared", raising=False)
    st.session_state.clear()
    st.session_state["profile_id"] = "alice"
    yield
    st.session_state.clear()


def _store():
    return ProfileStorage()


def test_fresh_profile_has_no_consent():
    assert consent.has_accepted_privacy(_store()) is False
    assert consent.owner_can_view(_store()) is False


def test_record_consent_sets_privacy_and_visibility():
    consent.record_consent(privacy_accepted=True, owner_visibility=True, store=_store())
    assert consent.has_accepted_privacy(_store()) is True
    assert consent.owner_can_view(_store()) is True


def test_revocation_is_timestamped_not_deleted():
    consent.record_consent(privacy_accepted=True, owner_visibility=True, store=_store())
    consent.set_owner_visibility(False, store=_store())
    c = consent.load_consent(_store())
    assert consent.owner_can_view(_store()) is False
    assert c["revoked_at"] is not None          # revocation recorded
    assert c["owner_visibility_consent_at"] is not None  # original grant kept


def test_re_granting_clears_revocation():
    consent.record_consent(privacy_accepted=True, owner_visibility=True, store=_store())
    consent.set_owner_visibility(False, store=_store())
    consent.set_owner_visibility(True, store=_store())
    c = consent.load_consent(_store())
    assert consent.owner_can_view(_store()) is True
    assert c["revoked_at"] is None


def test_privacy_acceptance_without_owner_visibility():
    consent.record_consent(privacy_accepted=True, owner_visibility=False, store=_store())
    assert consent.has_accepted_privacy(_store()) is True
    assert consent.owner_can_view(_store()) is False
