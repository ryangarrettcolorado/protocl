"""Tests for the DataSource abstraction layer (v3.8).

Coverage:

1. **ABC contract** — subclasses must implement the required methods; the
   default :meth:`validate_config` is a no-op; :meth:`empty_result` always
   produces a frame with the declared columns.

2. **Registry** — :func:`registry` returns at least Oura and never raises on
   missing optional dependencies.

3. **OuraDataSource** — full behavioural coverage:
   - configuration detection (env var, malformed PAT, missing PAT)
   - live gating (returns NOT_LIVE without ``OURA_LIVE``)
   - happy-path fetch with mocked ``requests`` (sleep + readiness merge)
   - sleep-only fetch when readiness endpoint errors
   - 401/403 → AUTH_ERROR
   - 429 → RATE_LIMITED
   - 500 → UPSTREAM_ERROR
   - transport exception → UPSTREAM_ERROR
   - empty payload → OK with zero-row frame in correct schema
   - schema conformance: every result frame has exactly the declared columns
   - seconds → hours conversion for sleep durations
   - contributor-score values pass through unchanged
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional

import pandas as pd
import pytest

from protocl.modules.data_sources import (
    ConfigError,
    DataSource,
    FetchResult,
    FetchStatus,
    registry,
)
from protocl.modules.data_sources.base import (
    WEARABLES_EXTENDED_COLUMNS,
    WEARABLES_COLUMNS,
    TRAINING_COLUMNS,
)
from protocl.modules.data_sources.oura import OuraDataSource, _seconds_to_hours
from protocl.modules.data_sources.whoop import WhoopDataSource, _ms_to_hours
from protocl.modules.data_sources.google_health import (
    GoogleHealthDataSource,
    _minutes_to_hours,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _MockResponse:
    """Stand-in for ``requests.Response`` — exposes only what we use."""

    status_code: int
    payload: Optional[Dict[str, Any]] = None
    raise_on_json: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Dict[str, Any]:
        if self.raise_on_json:
            raise ValueError("simulated decode failure")
        return self.payload or {}


def _mock_get(routing: Dict[str, _MockResponse]):
    """Build a ``request_fn`` stand-in routed by URL substring.

    Example::

        get = _mock_get({"daily_sleep": _MockResponse(200, {...}),
                         "daily_readiness": _MockResponse(200, {...})})
    """

    def _get(url, headers=None, params=None, timeout=None):
        for key, resp in routing.items():
            if key in url:
                return resp
        return _MockResponse(404, {})

    return _get


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Strip Oura-related env vars before every test so previous tests can't
    leak state. Restore is automatic via monkeypatch."""
    for key in (
        "OURA_PAT",
        "OURA_LIVE",
        "WHOOP_CLIENT_ID",
        "WHOOP_CLIENT_SECRET",
        "WHOOP_REFRESH_TOKEN",
        "WHOOP_LIVE",
        "GOOGLE_HEALTH_CLIENT_ID",
        "GOOGLE_HEALTH_CLIENT_SECRET",
        "GOOGLE_HEALTH_REFRESH_TOKEN",
        "GOOGLE_HEALTH_LIVE",
    ):
        monkeypatch.delenv(key, raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# ABC contract
# ─────────────────────────────────────────────────────────────────────────────


class TestDataSourceContract:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            DataSource()  # type: ignore[abstract]

    def test_validate_config_default_is_noop(self, monkeypatch):
        """Subclasses that don't override validate_config should not error."""
        monkeypatch.setenv("OURA_PAT", "x" * 40)
        OuraDataSource().validate_config()  # should not raise

    def test_empty_result_uses_declared_columns(self):
        source = OuraDataSource()
        result = source.empty_result(FetchStatus.NOT_CONFIGURED)
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS
        assert result.records_fetched == 0
        assert result.source_name == "oura"

    def test_fetch_result_ok_property(self):
        ok = FetchResult(FetchStatus.OK, pd.DataFrame(), source_name="oura")
        bad = FetchResult(
            FetchStatus.AUTH_ERROR, pd.DataFrame(), source_name="oura"
        )
        assert ok.ok is True
        assert bad.ok is False

    def test_fetch_result_empty_factory(self):
        result = FetchResult.empty(
            status=FetchStatus.RATE_LIMITED,
            columns=["a", "b", "c"],
            source_name="test",
            error_message="slow down",
        )
        assert list(result.frame.columns) == ["a", "b", "c"]
        assert result.error_message == "slow down"
        assert result.records_fetched == 0
        assert result.source_name == "test"

    def test_canonical_schema_constants_are_distinct(self):
        """Catch accidental column-list aliasing across schemas."""
        assert WEARABLES_COLUMNS != WEARABLES_EXTENDED_COLUMNS
        assert WEARABLES_COLUMNS != TRAINING_COLUMNS
        assert WEARABLES_EXTENDED_COLUMNS != TRAINING_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_registry_contains_oura(self):
        sources = registry()
        assert "oura" in sources
        assert isinstance(sources["oura"], OuraDataSource)

    def test_registry_contains_whoop(self):
        sources = registry()
        assert "whoop" in sources
        assert isinstance(sources["whoop"], WhoopDataSource)

    def test_registry_contains_google_health(self):
        sources = registry()
        assert "google_health" in sources
        assert isinstance(sources["google_health"], GoogleHealthDataSource)

    def test_registry_keys_match_source_names(self):
        for key, source in registry().items():
            assert key == source.name, (
                f"registry key {key!r} doesn't match source.name {source.name!r}"
            )

    def test_registry_call_does_not_raise(self):
        # The registry should be import-safe even when no source is configured.
        registry()  # should not raise


# ─────────────────────────────────────────────────────────────────────────────
# OuraDataSource — configuration
# ─────────────────────────────────────────────────────────────────────────────


class TestOuraConfiguration:
    def test_unconfigured_when_pat_missing(self):
        assert OuraDataSource().is_configured() is False

    def test_unconfigured_when_pat_too_short(self, monkeypatch):
        monkeypatch.setenv("OURA_PAT", "abc")
        assert OuraDataSource().is_configured() is False

    def test_configured_when_pat_present_and_long_enough(self, monkeypatch):
        monkeypatch.setenv("OURA_PAT", "x" * 40)
        assert OuraDataSource().is_configured() is True

    def test_validate_config_raises_on_malformed_pat(self, monkeypatch):
        monkeypatch.setenv("OURA_PAT", "short")
        with pytest.raises(ConfigError):
            OuraDataSource().validate_config()

    def test_validate_config_silent_when_unset(self):
        # Not configured ≠ broken. validate_config only catches the "set but
        # wrong" case; pure absence is handled by is_configured().
        OuraDataSource().validate_config()  # should not raise

    def test_is_live_defaults_false(self, monkeypatch):
        monkeypatch.setenv("OURA_PAT", "x" * 40)
        assert OuraDataSource().is_live() is False

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_is_live_honors_env_truthy(self, monkeypatch, value):
        monkeypatch.setenv("OURA_LIVE", value)
        assert OuraDataSource().is_live() is True

    @pytest.mark.parametrize("value", ["0", "false", "no", "", "off", "nah"])
    def test_is_live_honors_env_falsy(self, monkeypatch, value):
        monkeypatch.setenv("OURA_LIVE", value)
        assert OuraDataSource().is_live() is False


# ─────────────────────────────────────────────────────────────────────────────
# OuraDataSource — fetch gating
# ─────────────────────────────────────────────────────────────────────────────


class TestOuraFetchGating:
    def test_unconfigured_returns_not_configured(self):
        result = OuraDataSource().fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.NOT_CONFIGURED
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS
        assert result.records_fetched == 0

    def test_configured_but_not_live_returns_not_live(self, monkeypatch):
        monkeypatch.setenv("OURA_PAT", "x" * 40)
        # OURA_LIVE intentionally unset
        result = OuraDataSource().fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.NOT_LIVE
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# OuraDataSource — happy path
# ─────────────────────────────────────────────────────────────────────────────


_SAMPLE_SLEEP = {
    "data": [
        {
            "day": "2026-05-01",
            "total_sleep_duration": 28800,  # 8.0 h
            "deep_sleep_duration": 5400,  # 1.5 h
            "rem_sleep_duration": 7200,  # 2.0 h
            "contributors": {},
        },
        {
            "day": "2026-05-02",
            "total_sleep_duration": 25200,  # 7.0 h
            "deep_sleep_duration": 3600,  # 1.0 h
            "rem_sleep_duration": 5400,  # 1.5 h
            "contributors": {},
        },
    ]
}

_SAMPLE_READINESS = {
    "data": [
        {
            "day": "2026-05-01",
            "resting_heart_rate": 52,
            "hrv_balance": 65,
            "respiratory_rate": 14.2,
            "contributors": {},
        },
        {
            "day": "2026-05-02",
            "resting_heart_rate": 55,
            "hrv_balance": 60,
            "respiratory_rate": 14.5,
            "contributors": {},
        },
    ]
}


class TestOuraFetchHappyPath:
    def setup_method(self, _):
        os.environ["OURA_PAT"] = "x" * 40
        os.environ["OURA_LIVE"] = "1"

    def teardown_method(self, _):
        os.environ.pop("OURA_PAT", None)
        os.environ.pop("OURA_LIVE", None)

    def test_merges_sleep_and_readiness_into_canonical_frame(self):
        get = _mock_get(
            {
                "daily_sleep": _MockResponse(200, _SAMPLE_SLEEP),
                "daily_readiness": _MockResponse(200, _SAMPLE_READINESS),
            }
        )
        source = OuraDataSource(request_fn=get)
        result = source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))

        assert result.status is FetchStatus.OK
        assert result.records_fetched == 2
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

        rows = result.frame.to_dict(orient="records")
        # Row order matches sleep payload order.
        assert rows[0]["date"] == "2026-05-01"
        assert rows[0]["sleep_duration_hrs"] == 8.0
        assert rows[0]["sleep_deep_hrs"] == 1.5
        assert rows[0]["sleep_rem_hrs"] == 2.0
        assert rows[0]["resting_hr_bpm"] == 52
        assert rows[0]["hrv_sdnn_ms"] == 65
        assert rows[0]["respiratory_rate_brpm"] == 14.2
        assert rows[0]["source"] == "oura"

        assert rows[1]["date"] == "2026-05-02"
        assert rows[1]["sleep_duration_hrs"] == 7.0

    def test_handles_empty_sleep_payload(self):
        get = _mock_get(
            {
                "daily_sleep": _MockResponse(200, {"data": []}),
                "daily_readiness": _MockResponse(200, {"data": []}),
            }
        )
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 0
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

    def test_readiness_failure_is_non_fatal(self):
        """Sleep succeeds, readiness 500s — we still emit sleep-only rows."""
        get = _mock_get(
            {
                "daily_sleep": _MockResponse(200, _SAMPLE_SLEEP),
                "daily_readiness": _MockResponse(500, {}),
            }
        )
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 2
        # Heart-rate fields should be None (no readiness data).
        for _, row in result.frame.iterrows():
            assert row["resting_hr_bpm"] is None
            assert row["hrv_sdnn_ms"] is None

    def test_skips_rows_without_day_field(self):
        """Defensive: a payload without ``day`` shouldn't crash the mapper."""
        malformed = {"data": [{"total_sleep_duration": 28800}]}
        get = _mock_get(
            {
                "daily_sleep": _MockResponse(200, malformed),
                "daily_readiness": _MockResponse(200, {"data": []}),
            }
        )
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 1)
        )
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 0


# ─────────────────────────────────────────────────────────────────────────────
# OuraDataSource — error paths
# ─────────────────────────────────────────────────────────────────────────────


class TestOuraErrorHandling:
    def setup_method(self, _):
        os.environ["OURA_PAT"] = "x" * 40
        os.environ["OURA_LIVE"] = "1"

    def teardown_method(self, _):
        os.environ.pop("OURA_PAT", None)
        os.environ.pop("OURA_LIVE", None)

    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_error_codes_map_to_auth_error_status(self, code):
        get = _mock_get({"daily_sleep": _MockResponse(code, {})})
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.AUTH_ERROR
        assert str(code) in result.error_message
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

    def test_rate_limit_maps_to_rate_limited(self):
        get = _mock_get({"daily_sleep": _MockResponse(429, {})})
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.RATE_LIMITED
        assert "429" in result.error_message

    def test_server_error_maps_to_upstream_error(self):
        get = _mock_get({"daily_sleep": _MockResponse(503, {})})
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.UPSTREAM_ERROR
        assert "503" in result.error_message

    def test_transport_exception_maps_to_upstream_error(self):
        def _raise(*a, **kw):
            raise ConnectionError("network is down")

        result = OuraDataSource(request_fn=_raise).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.UPSTREAM_ERROR
        assert "network is down" in result.error_message

    def test_json_decode_failure_on_sleep_maps_to_upstream_error(self):
        get = _mock_get(
            {
                "daily_sleep": _MockResponse(200, None, raise_on_json=True),
                "daily_readiness": _MockResponse(200, {"data": []}),
            }
        )
        result = OuraDataSource(request_fn=get).fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.UPSTREAM_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestSecondsToHours:
    def test_converts_large_seconds_to_hours(self):
        assert _seconds_to_hours(28800) == 8.0  # 8 hours
        assert _seconds_to_hours(3600) == 1.0
        assert _seconds_to_hours(5400) == 1.5

    def test_passes_through_contributor_scores(self):
        # Values <=100 are treated as contributor scores (0-100), not seconds.
        assert _seconds_to_hours(85) == 85.0
        assert _seconds_to_hours(0) == 0.0

    def test_none_in_none_out(self):
        assert _seconds_to_hours(None) is None

    def test_non_numeric_returns_none(self):
        assert _seconds_to_hours("not a number") is None

    def test_rounds_to_two_decimals(self):
        # 7h 32m 17s = 27137 seconds ≈ 7.54 hours
        assert _seconds_to_hours(27137) == 7.54


# ─────────────────────────────────────────────────────────────────────────────
# OAuth2DataSource scaffolding — token refresh + caching + error mapping
# ─────────────────────────────────────────────────────────────────────────────


def _whoop_env(monkeypatch):
    """Helper to make Whoop fully configured + live."""
    monkeypatch.setenv("WHOOP_CLIENT_ID", "cid")
    monkeypatch.setenv("WHOOP_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "rtok")
    monkeypatch.setenv("WHOOP_LIVE", "1")


def _google_env(monkeypatch):
    """Helper to make Google Health fully configured + live."""
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_ID", "gcid")
    monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRET", "gsecret")
    monkeypatch.setenv("GOOGLE_HEALTH_REFRESH_TOKEN", "grtok")
    monkeypatch.setenv("GOOGLE_HEALTH_LIVE", "1")


def _mock_post_success(token: str = "access-abc", expires_in: int = 3600):
    """Build a POST mock that always returns a successful token-refresh body."""
    calls = []

    def _post(url, data=None, timeout=None):
        calls.append({"url": url, "data": data, "timeout": timeout})
        return _MockResponse(
            200, {"access_token": token, "expires_in": expires_in, "token_type": "Bearer"}
        )

    _post.calls = calls  # type: ignore[attr-defined]
    return _post


class TestOAuth2Refresh:
    def test_partial_config_is_not_configured(self, monkeypatch):
        monkeypatch.setenv("WHOOP_CLIENT_ID", "cid")
        # client_secret + refresh_token intentionally missing
        assert WhoopDataSource().is_configured() is False

    def test_full_config_is_configured(self, monkeypatch):
        _whoop_env(monkeypatch)
        assert WhoopDataSource().is_configured() is True

    def test_validate_config_raises_on_partial_credentials(self, monkeypatch):
        monkeypatch.setenv("WHOOP_CLIENT_ID", "cid")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "csecret")
        # refresh_token missing → partial
        with pytest.raises(ConfigError):
            WhoopDataSource().validate_config()

    def test_validate_config_silent_when_fully_unset(self):
        WhoopDataSource().validate_config()  # should not raise

    def test_validate_config_silent_when_fully_set(self, monkeypatch):
        _whoop_env(monkeypatch)
        WhoopDataSource().validate_config()  # should not raise

    def test_live_gate_defaults_false(self, monkeypatch):
        monkeypatch.setenv("WHOOP_CLIENT_ID", "cid")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "rtok")
        # WHOOP_LIVE intentionally unset
        assert WhoopDataSource().is_live() is False

    def test_unconfigured_returns_not_configured(self):
        result = WhoopDataSource().fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.NOT_CONFIGURED

    def test_configured_but_not_live_returns_not_live(self, monkeypatch):
        monkeypatch.setenv("WHOOP_CLIENT_ID", "cid")
        monkeypatch.setenv("WHOOP_CLIENT_SECRET", "csecret")
        monkeypatch.setenv("WHOOP_REFRESH_TOKEN", "rtok")
        result = WhoopDataSource().fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.NOT_LIVE

    def test_token_refresh_failure_maps_to_auth_error(self, monkeypatch):
        _whoop_env(monkeypatch)

        def _post(url, data=None, timeout=None):
            return _MockResponse(401, {"error": "invalid_grant"})

        source = WhoopDataSource(post_fn=_post, request_fn=_mock_get({}))
        result = source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.AUTH_ERROR
        assert "401" in result.error_message

    def test_token_response_missing_access_token_is_auth_error(self, monkeypatch):
        _whoop_env(monkeypatch)

        def _post(url, data=None, timeout=None):
            return _MockResponse(200, {"expires_in": 3600})  # no access_token

        source = WhoopDataSource(post_fn=_post, request_fn=_mock_get({}))
        result = source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.AUTH_ERROR

    def test_token_refresh_transport_error_maps_to_upstream(self, monkeypatch):
        _whoop_env(monkeypatch)

        def _post(*a, **kw):
            raise ConnectionError("token DNS failure")

        source = WhoopDataSource(post_fn=_post, request_fn=_mock_get({}))
        result = source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.UPSTREAM_ERROR
        assert "DNS" in result.error_message

    def test_token_is_cached_between_calls(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "recovery": _MockResponse(200, {"records": []}),
                "activity/sleep": _MockResponse(200, {"records": []}),
                "cycle": _MockResponse(200, {"records": []}),
            }
        )
        source = WhoopDataSource(post_fn=post, request_fn=get, clock_fn=lambda: 1000.0)

        source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        source.fetch_window(date(2026, 5, 8), date(2026, 5, 14))

        # Token endpoint should only be hit once across two fetch_window calls.
        assert len(post.calls) == 1
        assert post.calls[0]["data"]["grant_type"] == "refresh_token"
        assert post.calls[0]["data"]["client_id"] == "cid"
        assert post.calls[0]["data"]["refresh_token"] == "rtok"
        assert post.calls[0]["data"]["scope"] == WhoopDataSource.token_scope

    def test_token_refresh_on_expiry(self, monkeypatch):
        _whoop_env(monkeypatch)
        # Each successful refresh returns a token valid for 100s; we'll bump
        # the clock past it between calls and confirm a second refresh fires.
        post = _mock_post_success(expires_in=100)
        get = _mock_get(
            {
                "recovery": _MockResponse(200, {"records": []}),
                "activity/sleep": _MockResponse(200, {"records": []}),
                "cycle": _MockResponse(200, {"records": []}),
            }
        )
        clock_state = {"now": 1000.0}
        source = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: clock_state["now"]
        )
        source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        # Advance clock past expiry buffer (token good until 1100, buffer 60s).
        clock_state["now"] = 1100.0
        source.fetch_window(date(2026, 5, 8), date(2026, 5, 14))
        assert len(post.calls) == 2

    def test_401_on_api_invalidates_cached_token(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"recovery": _MockResponse(401, {})})
        source = WhoopDataSource(post_fn=post, request_fn=get, clock_fn=lambda: 1000.0)
        result = source.fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.AUTH_ERROR
        # Token cache should have been cleared by the 401.
        assert source._token_cache is None


# ─────────────────────────────────────────────────────────────────────────────
# WhoopDataSource — happy path
# ─────────────────────────────────────────────────────────────────────────────


_WHOOP_RECOVERY = {
    "records": [
        {
            "created_at": "2026-05-01T07:00:00Z",
            "score": {
                "resting_heart_rate": 53,
                "hrv_rmssd_milli": 62.5,
                "respiratory_rate": 14.1,
            },
        },
        {
            "created_at": "2026-05-02T07:05:00Z",
            "score": {
                "resting_heart_rate": 55,
                "hrv_rmssd_milli": 58.0,
                "respiratory_rate": 14.3,
            },
        },
    ]
}

_WHOOP_SLEEP = {
    "records": [
        {
            "created_at": "2026-05-01T07:30:00Z",
            "score": {
                "stage_summary": {
                    "total_slow_wave_sleep_time_milli": 5_400_000,  # 1.5h
                    "total_rem_sleep_time_milli": 7_200_000,  # 2.0h
                },
                "total_in_bed_time_milli": 28_800_000,  # 8.0h
            },
        },
        {
            "created_at": "2026-05-02T07:30:00Z",
            "score": {
                "stage_summary": {
                    "total_slow_wave_sleep_time_milli": 3_600_000,  # 1.0h
                    "total_rem_sleep_time_milli": 5_400_000,  # 1.5h
                },
                "total_in_bed_time_milli": 25_200_000,  # 7.0h
            },
        },
    ]
}

_WHOOP_CYCLE = {
    "records": [
        {
            "created_at": "2026-05-01T07:00:00Z",
            "score": {"average_heart_rate": 70},
        }
    ]
}


class TestWhoopFetchHappyPath:
    def test_merges_recovery_sleep_cycle(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "recovery": _MockResponse(200, _WHOOP_RECOVERY),
                "activity/sleep": _MockResponse(200, _WHOOP_SLEEP),
                "cycle": _MockResponse(200, _WHOOP_CYCLE),
            }
        )
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))

        assert result.status is FetchStatus.OK
        assert result.records_fetched == 2
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

        rows = result.frame.to_dict(orient="records")
        assert rows[0]["date"] == "2026-05-01"
        assert rows[0]["sleep_duration_hrs"] == 8.0
        assert rows[0]["sleep_deep_hrs"] == 1.5
        assert rows[0]["sleep_rem_hrs"] == 2.0
        assert rows[0]["resting_hr_bpm"] == 53
        assert rows[0]["hrv_sdnn_ms"] == 62.5
        assert rows[0]["respiratory_rate_brpm"] == 14.1
        assert rows[0]["source"] == "whoop"

        assert rows[1]["date"] == "2026-05-02"
        assert rows[1]["sleep_duration_hrs"] == 7.0
        assert rows[1]["resting_hr_bpm"] == 55

    def test_sleep_failure_is_non_fatal(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "recovery": _MockResponse(200, _WHOOP_RECOVERY),
                "activity/sleep": _MockResponse(500, {}),
                "cycle": _MockResponse(200, {"records": []}),
            }
        )
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 2
        for _, row in result.frame.iterrows():
            assert row["sleep_duration_hrs"] is None
            assert row["sleep_deep_hrs"] is None
            assert row["sleep_rem_hrs"] is None

    def test_empty_recovery_yields_empty_frame_in_schema(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "recovery": _MockResponse(200, {"records": []}),
                "activity/sleep": _MockResponse(200, {"records": []}),
                "cycle": _MockResponse(200, {"records": []}),
            }
        )
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 0
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

    def test_cycle_fallback_when_recovery_lacks_resting_hr(self, monkeypatch):
        _whoop_env(monkeypatch)
        recovery_no_hr = {
            "records": [
                {
                    "created_at": "2026-05-01T07:00:00Z",
                    "score": {"hrv_rmssd_milli": 62.5, "respiratory_rate": 14.1},
                }
            ]
        }
        post = _mock_post_success()
        get = _mock_get(
            {
                "recovery": _MockResponse(200, recovery_no_hr),
                "activity/sleep": _MockResponse(200, {"records": []}),
                "cycle": _MockResponse(200, _WHOOP_CYCLE),
            }
        )
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        # Resting HR backfilled from cycle.average_heart_rate
        assert result.frame.iloc[0]["resting_hr_bpm"] == 70


# ─────────────────────────────────────────────────────────────────────────────
# WhoopDataSource — error handling
# ─────────────────────────────────────────────────────────────────────────────


class TestWhoopErrorHandling:
    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_error_codes(self, monkeypatch, code):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"recovery": _MockResponse(code, {})})
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.AUTH_ERROR
        assert str(code) in result.error_message

    def test_rate_limit_maps_to_rate_limited(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"recovery": _MockResponse(429, {})})
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.RATE_LIMITED

    def test_server_error_maps_to_upstream(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"recovery": _MockResponse(502, {})})
        result = WhoopDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.UPSTREAM_ERROR

    def test_transport_exception_maps_to_upstream(self, monkeypatch):
        _whoop_env(monkeypatch)
        post = _mock_post_success()

        def _raise(*a, **kw):
            raise ConnectionError("recovery DNS failure")

        result = WhoopDataSource(
            post_fn=post, request_fn=_raise, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.UPSTREAM_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# GoogleHealthDataSource — happy path
# ─────────────────────────────────────────────────────────────────────────────


_GOOGLE_SLEEP = {
    "dataPoints": [
        {
            "date": "2026-05-01",
            "totalDurationMinutes": 480,  # 8.0h
            "respiratoryRate": 14.2,
            "stages": {"deepMinutes": 90, "remMinutes": 120},
        },
        {
            "date": "2026-05-02",
            "totalDurationMinutes": 420,  # 7.0h
            "respiratoryRate": 14.4,
            "stages": {"deepMinutes": 60, "remMinutes": 90},
        },
    ]
}

_GOOGLE_HR = {
    "dataPoints": [
        {"date": "2026-05-01", "restingHeartRate": 54},
        {"date": "2026-05-02", "restingHeartRate": 56},
    ]
}

_GOOGLE_HRV = {
    "dataPoints": [
        {"date": "2026-05-01", "hrvRmssd": 60.5},
        {"date": "2026-05-02", "hrvRmssd": 57.2},
    ]
}


class TestGoogleHealthFetchHappyPath:
    def test_merges_sleep_hr_hrv(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(200, _GOOGLE_SLEEP),
                "/heartrate": _MockResponse(200, _GOOGLE_HR),
                "/hrv": _MockResponse(200, _GOOGLE_HRV),
            }
        )
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))

        assert result.status is FetchStatus.OK
        assert result.records_fetched == 2
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS

        rows = result.frame.to_dict(orient="records")
        assert rows[0]["date"] == "2026-05-01"
        assert rows[0]["sleep_duration_hrs"] == 8.0
        assert rows[0]["sleep_deep_hrs"] == 1.5
        assert rows[0]["sleep_rem_hrs"] == 2.0
        assert rows[0]["resting_hr_bpm"] == 54
        assert rows[0]["hrv_sdnn_ms"] == 60.5
        assert rows[0]["respiratory_rate_brpm"] == 14.2
        assert rows[0]["source"] == "google_health"

    def test_accepts_records_key_variant(self, monkeypatch):
        """Google Health bundles vary — accept ``records`` as well as ``dataPoints``."""
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(
                    200,
                    {"records": [{"date": "2026-05-01", "totalDurationMinutes": 480}]},
                ),
                "/heartrate": _MockResponse(200, {"data": []}),
                "/hrv": _MockResponse(200, {"records": []}),
            }
        )
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 1
        assert result.frame.iloc[0]["sleep_duration_hrs"] == 8.0

    def test_accepts_snake_case_keys(self, monkeypatch):
        """Some Google Health endpoints emit snake_case payload keys."""
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(
                    200,
                    {
                        "dataPoints": [
                            {
                                "date": "2026-05-01",
                                "total_duration_minutes": 480,
                                "respiratory_rate": 14.0,
                                "stages": {"deep_minutes": 90, "rem_minutes": 120},
                            }
                        ]
                    },
                ),
                "/heartrate": _MockResponse(
                    200,
                    {"dataPoints": [{"date": "2026-05-01", "resting_heart_rate": 54}]},
                ),
                "/hrv": _MockResponse(
                    200, {"dataPoints": [{"date": "2026-05-01", "hrv_rmssd": 60.0}]}
                ),
            }
        )
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        row = result.frame.iloc[0]
        assert row["sleep_duration_hrs"] == 8.0
        assert row["sleep_deep_hrs"] == 1.5
        assert row["sleep_rem_hrs"] == 2.0
        assert row["resting_hr_bpm"] == 54
        assert row["hrv_sdnn_ms"] == 60.0
        assert row["respiratory_rate_brpm"] == 14.0

    def test_hr_failure_is_non_fatal(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(200, _GOOGLE_SLEEP),
                "/heartrate": _MockResponse(500, {}),
                "/hrv": _MockResponse(200, _GOOGLE_HRV),
            }
        )
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        # HR missing for both rows; HRV still present.
        for _, row in result.frame.iterrows():
            assert row["resting_hr_bpm"] is None
            assert row["hrv_sdnn_ms"] is not None

    def test_empty_sleep_yields_empty_frame_in_schema(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(200, {"dataPoints": []}),
                "/heartrate": _MockResponse(200, {"dataPoints": []}),
                "/hrv": _MockResponse(200, {"dataPoints": []}),
            }
        )
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.OK
        assert result.records_fetched == 0
        assert list(result.frame.columns) == WEARABLES_EXTENDED_COLUMNS


# ─────────────────────────────────────────────────────────────────────────────
# GoogleHealthDataSource — error handling
# ─────────────────────────────────────────────────────────────────────────────


class TestGoogleHealthErrorHandling:
    def test_unconfigured_returns_not_configured(self):
        result = GoogleHealthDataSource().fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.NOT_CONFIGURED

    def test_configured_but_not_live_returns_not_live(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_ID", "gcid")
        monkeypatch.setenv("GOOGLE_HEALTH_CLIENT_SECRET", "gsecret")
        monkeypatch.setenv("GOOGLE_HEALTH_REFRESH_TOKEN", "grtok")
        result = GoogleHealthDataSource().fetch_window(
            date(2026, 5, 1), date(2026, 5, 7)
        )
        assert result.status is FetchStatus.NOT_LIVE

    @pytest.mark.parametrize("code", [401, 403])
    def test_auth_errors_on_sleep_propagate(self, monkeypatch, code):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"/sleep": _MockResponse(code, {})})
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.AUTH_ERROR

    def test_rate_limit_on_sleep_propagates(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"/sleep": _MockResponse(429, {})})
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.RATE_LIMITED

    def test_server_error_on_sleep_propagates(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get({"/sleep": _MockResponse(503, {})})
        result = GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert result.status is FetchStatus.UPSTREAM_ERROR

    def test_token_endpoint_targets_google_oauth(self, monkeypatch):
        _google_env(monkeypatch)
        post = _mock_post_success()
        get = _mock_get(
            {
                "/sleep": _MockResponse(200, {"dataPoints": []}),
                "/heartrate": _MockResponse(200, {"dataPoints": []}),
                "/hrv": _MockResponse(200, {"dataPoints": []}),
            }
        )
        GoogleHealthDataSource(
            post_fn=post, request_fn=get, clock_fn=lambda: 1000.0
        ).fetch_window(date(2026, 5, 1), date(2026, 5, 7))
        assert post.calls[0]["url"] == "https://oauth2.googleapis.com/token"


# ─────────────────────────────────────────────────────────────────────────────
# Unit conversion helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestMsToHours:
    def test_basic_conversions(self):
        assert _ms_to_hours(3_600_000) == 1.0
        assert _ms_to_hours(28_800_000) == 8.0
        assert _ms_to_hours(0) == 0.0

    def test_none_in_none_out(self):
        assert _ms_to_hours(None) is None

    def test_non_numeric_returns_none(self):
        assert _ms_to_hours("nope") is None

    def test_rounds_to_two_decimals(self):
        # 7h 32m 17s = 27_137_000 ms ≈ 7.54 h
        assert _ms_to_hours(27_137_000) == 7.54


class TestMinutesToHours:
    def test_basic_conversions(self):
        assert _minutes_to_hours(60) == 1.0
        assert _minutes_to_hours(480) == 8.0
        assert _minutes_to_hours(0) == 0.0

    def test_none_in_none_out(self):
        assert _minutes_to_hours(None) is None

    def test_non_numeric_returns_none(self):
        assert _minutes_to_hours("nope") is None

    def test_rounds_to_two_decimals(self):
        # 90 minutes = 1.5 h, 75 minutes = 1.25 h
        assert _minutes_to_hours(90) == 1.5
        assert _minutes_to_hours(75) == 1.25
