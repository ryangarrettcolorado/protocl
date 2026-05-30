"""v3.5 — error capture: hashing, dedup window, grouping, fixed-state."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import error_capture as ec


NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def _raise(kind, msg):
    try:
        raise kind(msg)
    except kind as e:
        return e


def test_traceback_hash_stable_per_type():
    e1 = _raise(ValueError, "boom")
    e2 = _raise(ValueError, "boom")
    e3 = _raise(KeyError, "boom")
    assert ec.traceback_hash(e1) == ec.traceback_hash(e2)
    assert ec.traceback_hash(e1) != ec.traceback_hash(e3)


def test_capture_writes_row(isolate):
    th = ec.capture_error(_raise(ValueError, "boom"), page="home", profile_id="alice", now=NOW)
    df = ec.read_errors()
    assert len(df) == 1
    assert df.iloc[0]["traceback_hash"] == th
    assert df.iloc[0]["exception_type"] == "ValueError"
    assert df.iloc[0]["user_facing_message"] == ec.USER_FACING_MESSAGE


def test_dedup_within_window(isolate):
    e = _raise(ValueError, "boom")
    ec.capture_error(e, page="home", now=NOW)
    # Same hash 30 min later → deduped (not appended).
    ec.capture_error(e, page="home", now=NOW + timedelta(minutes=30))
    assert len(ec.read_errors()) == 1
    # Beyond the window → new row.
    ec.capture_error(e, page="home", now=NOW + timedelta(hours=2))
    assert len(ec.read_errors()) == 2


def test_group_by_hash_counts(isolate):
    for i in range(3):
        ec.capture_error(_raise(ValueError, "boom"), now=NOW + timedelta(hours=2 * i))
    ec.capture_error(_raise(KeyError, "missing"), now=NOW)
    grouped = ec.group_by_hash(since_hours=240, now=NOW + timedelta(hours=5))
    counts = dict(zip(grouped["exception_type"], grouped["count"]))
    assert counts["ValueError"] == 3
    assert counts["KeyError"] == 1


def test_mark_fixed_roundtrip(isolate):
    th = ec.capture_error(_raise(ValueError, "boom"), now=NOW)
    assert th not in ec.fixed_hashes()
    ec.mark_fixed(th)
    assert th in ec.fixed_hashes()
