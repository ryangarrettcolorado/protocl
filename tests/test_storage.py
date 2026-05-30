"""v3.2 — ProfileStorage isolation, traversal rejection, read-only guard."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st
import storage
from storage import ProfileStorage, ReadOnlyError


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Point every storage path at a temp dir and reset session state."""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(storage, "SHARED_DIR", tmp_path / "shared")
    monkeypatch.setattr(storage, "SAMPLES_DIR", tmp_path / "samples")
    monkeypatch.setattr(storage, "OWNER_LEGACY_DIR", tmp_path / "ryan")
    st.session_state.clear()
    yield
    st.session_state.clear()


def test_profile_id_comes_from_session_not_constructor():
    st.session_state["profile_id"] = "friend_at_gmail_com"
    store = ProfileStorage()
    assert store.profile_id == "friend_at_gmail_com"
    # Constructor accepts no profile arg.
    with pytest.raises(TypeError):
        ProfileStorage("someone_else")  # type: ignore[call-arg]


def test_owner_uses_legacy_dir(tmp_path):
    st.session_state["profile_id"] = "ryan"
    store = ProfileStorage()
    assert store.profile_dir == tmp_path / "ryan"


def test_beta_user_uses_profiles_subdir(tmp_path):
    st.session_state["profile_id"] = "friend_at_gmail_com"
    store = ProfileStorage()
    assert store.profile_dir == tmp_path / "profiles" / "friend_at_gmail_com"


def test_two_users_never_share_a_directory():
    st.session_state["profile_id"] = "alice"
    a = ProfileStorage().profile_dir
    st.session_state["profile_id"] = "bob"
    b = ProfileStorage().profile_dir
    assert a != b


def test_writes_are_isolated_per_profile():
    st.session_state["profile_id"] = "alice"
    ProfileStorage().append_csv("daily_log.csv", {"date": "2026-01-01", "mood": "good"})
    # Bob sees nothing.
    st.session_state["profile_id"] = "bob"
    assert ProfileStorage().read_csv("daily_log.csv").empty
    # Alice still sees her own row.
    st.session_state["profile_id"] = "alice"
    df = ProfileStorage().read_csv("daily_log.csv")
    assert len(df) == 1 and df.iloc[0]["mood"] == "good"


@pytest.mark.parametrize("bad", ["../escape.csv", "a/b.csv", "..\\win.csv", "", ".", ".."])
def test_path_traversal_rejected(bad):
    st.session_state["profile_id"] = "alice"
    with pytest.raises(ValueError):
        ProfileStorage().get_path(bad)


def test_read_only_blocks_all_writes():
    st.session_state["profile_id"] = "alice"
    st.session_state["read_only"] = True
    store = ProfileStorage()
    with pytest.raises(ReadOnlyError):
        store.write_csv("x.csv", pd.DataFrame([{"a": 1}]))
    with pytest.raises(ReadOnlyError):
        store.append_csv("x.csv", {"a": 1})
    with pytest.raises(ReadOnlyError):
        store.write_json("x.json", {"a": 1})
    with pytest.raises(ReadOnlyError):
        store.seed_empty()


def test_read_only_still_allows_reads():
    st.session_state["profile_id"] = "alice"
    st.session_state["read_only"] = False
    ProfileStorage().append_csv("daily_log.csv", {"date": "2026-01-01"})
    st.session_state["read_only"] = True
    assert len(ProfileStorage().read_csv("daily_log.csv")) == 1


def test_seed_empty_creates_templates():
    st.session_state["profile_id"] = "newbie"
    store = ProfileStorage()
    store.seed_empty()
    assert store.get_path("bloodwork.csv").exists()
    assert store.get_path("protocol.csv").exists()
