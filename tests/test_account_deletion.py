"""v3.5 — account deletion: owner guard, PII scrub, soft-delete, restore."""
from __future__ import annotations

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

import storage
from modules import account_deletion as ad


def test_owner_cannot_be_deleted():
    assert ad.can_delete("ryan") is False
    assert ad.can_delete("alice_at_gmail_com") is True


def test_delete_account_refuses_owner(isolate):
    store = make_store("ryan")
    store.seed_empty()
    with pytest.raises(ValueError):
        ad.delete_account(store)


def test_scrub_replaces_profile_id_keeps_rows(isolate):
    storage.append_shared_csv(
        "all_feedback.csv",
        {"timestamp": "2026-01-01T00:00:00+00:00", "profile_id": "alice",
         "display_name": "Alice", "page": "home", "message": "hi"},
        ["timestamp", "profile_id", "display_name", "page", "message"],
    )
    storage.append_shared_csv(
        "all_feedback.csv",
        {"timestamp": "2026-01-02T00:00:00+00:00", "profile_id": "bob",
         "display_name": "Bob", "page": "home", "message": "yo"},
        ["timestamp", "profile_id", "display_name", "page", "message"],
    )
    result = ad.scrub_shared_logs("alice", logs=("all_feedback.csv",))
    assert result["all_feedback.csv"] == 1
    df = storage.read_shared_csv("all_feedback.csv")
    # Row count preserved, alice anonymized, bob untouched.
    assert len(df) == 2
    pids = set(df["profile_id"].astype(str))
    assert "alice" not in pids
    assert any(p.startswith("deleted_") for p in pids)
    assert "bob" in pids
    alice_row = df[df["profile_id"].astype(str).str.startswith("deleted_")].iloc[0]
    # Blanked display_name round-trips from CSV as NaN/empty — never "Alice".
    assert str(alice_row["display_name"]) in ("", "nan")
    # Timestamp retained for the audit trail.
    assert str(alice_row["timestamp"]).startswith("2026-01-01")


def test_soft_delete_archives_and_removes(isolate):
    store = make_store("alice_at_gmail_com")
    store.seed_empty()
    store.write_json("preferences.json", {"x": 1})
    assert store.profile_dir.exists()
    zip_path = ad.soft_delete_profile(store)
    assert zip_path is not None and zip_path.exists()
    assert not store.profile_dir.exists()


def test_full_delete_then_listed_and_restorable(isolate):
    store = make_store("carol_at_gmail_com")
    store.seed_empty()
    report = ad.delete_account(store, display_name="Carol")
    assert report["zip_path"] is not None
    archives = ad.list_soft_deleted()
    assert len(archives) == 1
    # Restore brings the directory back.
    ad.restore_from_soft_delete(archives[0]["zip"])
    restored = make_store("carol_at_gmail_com")
    assert restored.profile_dir.exists()
