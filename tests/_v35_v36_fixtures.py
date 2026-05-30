"""Shared fixtures for v3.5/v3.6 tests — storage isolation + path setup."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

import streamlit as st  # noqa: E402
import storage  # noqa: E402


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    """Point storage paths at a temp dir and reset session state."""
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "PROFILES_DIR", tmp_path / "profiles")
    monkeypatch.setattr(storage, "SHARED_DIR", tmp_path / "shared")
    monkeypatch.setattr(storage, "SAMPLES_DIR", tmp_path / "samples")
    monkeypatch.setattr(storage, "OWNER_LEGACY_DIR", tmp_path / "ryan")
    st.session_state.clear()
    yield tmp_path
    st.session_state.clear()


def make_store(profile_id: str):
    """A writable ProfileStorage bound to ``profile_id``."""
    st.session_state["profile_id"] = profile_id
    s = storage.ProfileStorage()
    s.read_only = False
    return s
