"""Oura Cloud API v2 — concrete :class:`DataSource` implementation.

Why Oura first
--------------

Oura is the simplest of the four direct wearable integrations because the
Cloud API v2 accepts a long-lived **Personal Access Token (PAT)** — no OAuth
dance, no refresh tokens, no consent webhook. The user generates a PAT in
their Oura account once and pastes it into Streamlit Cloud secrets as
``OURA_PAT``. From that moment forward every ``fetch_window`` call hits the
Oura cloud directly as the authenticated owner.

This makes Oura the ideal first implementation of the :class:`DataSource`
abstraction — it exercises every contract method without the OAuth complexity
that Whoop and Google Health will bring.

Endpoints used
--------------

- ``GET /v2/usercollection/daily_sleep`` — sleep duration, stages, score
- ``GET /v2/usercollection/daily_readiness`` — resting HR, HRV, respiratory rate

We merge by ``day`` and emit one row per calendar date in the canonical
extended wearables schema (see :data:`base.WEARABLES_EXTENDED_COLUMNS`).

Operational gates
-----------------

- **PAT presence**: ``is_configured()`` checks both ``st.secrets`` and the
  ``OURA_PAT`` environment variable so local pytest runs work without
  Streamlit.
- **Live flag**: ``is_live()`` checks the ``OURA_LIVE`` env var (default
  ``False``). Lets us ship a fully-tested integration that stays dormant
  until the operator explicitly flips it on per environment.
- **Timeout**: Every HTTP call has a 30-second timeout. Failures degrade to
  an empty frame with the right schema and a populated ``error_message``.

Rate limits
-----------

Oura caps at 5000 requests/day and 300/minute (per
``https://api.ouraring.com/docs/``). A daily window pull is 2 requests, so
the rate limit only matters in catastrophic backfill scenarios. We do not
currently implement client-side throttling.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

import pandas as pd

try:
    import streamlit as st  # type: ignore
except ImportError:  # pragma: no cover - exercised in unit tests
    st = None  # type: ignore

from .base import (
    ConfigError,
    DataSource,
    FetchResult,
    FetchStatus,
    WEARABLES_EXTENDED_COLUMNS,
)


_API_BASE = "https://api.ouraring.com/v2/usercollection"
_HTTP_TIMEOUT_S = 30
_DEFAULT_REQUEST_FN = None  # late-bound to ``requests.get`` so tests can patch


def _secret(key: str) -> Optional[str]:
    """Read a secret from Streamlit secrets, falling back to env var.

    Streamlit's ``st.secrets`` raises if no ``secrets.toml`` exists, so we
    guard it inside ``try/except`` to keep pytest runs (where Streamlit
    secrets are absent) happy.
    """
    if st is not None:
        try:
            if key in st.secrets:  # type: ignore[operator]
                return st.secrets[key]
        except Exception:
            pass
    return os.environ.get(key)


def _env_truthy(key: str) -> bool:
    value = (os.environ.get(key) or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


# ─────────────────────────────────────────────────────────────────────────────
# OuraDataSource
# ─────────────────────────────────────────────────────────────────────────────


class OuraDataSource(DataSource):
    """Concrete :class:`DataSource` for Oura Cloud API v2."""

    name = "oura"
    display_name = "Oura Ring"
    canonical_schema = "wearables"
    columns = WEARABLES_EXTENDED_COLUMNS

    # PAT length sanity check. Oura PATs are opaque strings ~32+ chars; we
    # only assert minimum length to catch obvious paste errors.
    _MIN_PAT_LENGTH = 20

    def __init__(self, *, request_fn=None) -> None:
        """``request_fn`` is injectable so tests can avoid a network round-trip.

        Defaults to ``requests.get`` lazily (imported on first use) so the
        module imports cleanly even when ``requests`` is absent.
        """
        self._request_fn = request_fn

    # ── lifecycle ────────────────────────────────────────────────────────

    def is_configured(self) -> bool:
        pat = _secret("OURA_PAT")
        return bool(pat) and len(pat.strip()) >= self._MIN_PAT_LENGTH

    def is_live(self) -> bool:
        # Default: only go live when explicitly enabled. Keeps dev/test safe.
        return _env_truthy("OURA_LIVE")

    def validate_config(self) -> None:
        pat = _secret("OURA_PAT")
        if pat is None:
            return  # not configured at all — caller handles via is_configured()
        if not isinstance(pat, str) or len(pat.strip()) < self._MIN_PAT_LENGTH:
            raise ConfigError(
                "OURA_PAT is set but looks malformed "
                f"(length {len(pat) if isinstance(pat, str) else 'n/a'}, "
                f"expected >={self._MIN_PAT_LENGTH})."
            )

    # ── data retrieval ───────────────────────────────────────────────────

    def fetch_window(self, start: date, end: date) -> FetchResult:
        if not self.is_configured():
            return self.empty_result(FetchStatus.NOT_CONFIGURED)
        if not self.is_live():
            return self.empty_result(FetchStatus.NOT_LIVE)

        get = self._resolve_request_fn()
        if get is None:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message="`requests` library not installed",
            )

        headers = {"Authorization": f"Bearer {_secret('OURA_PAT')}"}
        params = {"start_date": start.isoformat(), "end_date": end.isoformat()}

        # ── Sleep endpoint ─────────────────────────────────────────────
        try:
            r_sleep = get(
                f"{_API_BASE}/daily_sleep",
                headers=headers,
                params=params,
                timeout=_HTTP_TIMEOUT_S,
            )
        except Exception as exc:  # network blew up
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"daily_sleep transport error: {exc}",
            )

        status_check = self._classify_response(r_sleep, "daily_sleep")
        if status_check is not None:
            return status_check

        # ── Readiness endpoint ─────────────────────────────────────────
        try:
            r_ready = get(
                f"{_API_BASE}/daily_readiness",
                headers=headers,
                params=params,
                timeout=_HTTP_TIMEOUT_S,
            )
        except Exception as exc:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"daily_readiness transport error: {exc}",
            )

        # Readiness failures are non-fatal — we can still emit sleep-only rows.
        ready_rows: dict = {}
        if getattr(r_ready, "status_code", 500) == 200:
            try:
                ready_rows = {
                    d["day"]: d for d in (r_ready.json().get("data", []) or [])
                }
            except Exception:
                ready_rows = {}

        # ── Merge + map ────────────────────────────────────────────────
        try:
            sleep_payload = r_sleep.json().get("data", []) or []
        except Exception as exc:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"daily_sleep JSON decode failed: {exc}",
            )

        frame = self._map_to_wearables(sleep_payload, ready_rows)
        return FetchResult(
            status=FetchStatus.OK,
            frame=frame,
            records_fetched=len(frame),
            source_name=self.name,
        )

    # ── internals ────────────────────────────────────────────────────────

    def _resolve_request_fn(self):
        if self._request_fn is not None:
            return self._request_fn
        global _DEFAULT_REQUEST_FN
        if _DEFAULT_REQUEST_FN is None:
            try:
                import requests  # noqa: WPS433 — runtime optional dep

                _DEFAULT_REQUEST_FN = requests.get
            except ImportError:
                return None
        return _DEFAULT_REQUEST_FN

    def _classify_response(self, response, label: str) -> Optional[FetchResult]:
        """Inspect the response. Return a populated FetchResult on failure,
        or ``None`` if the response is OK to continue processing."""
        code = getattr(response, "status_code", None)
        if code == 200:
            return None
        if code in (401, 403):
            return self.empty_result(
                FetchStatus.AUTH_ERROR,
                error_message=f"{label} rejected credentials (HTTP {code})",
            )
        if code == 429:
            return self.empty_result(
                FetchStatus.RATE_LIMITED,
                error_message=f"{label} rate-limited (HTTP 429)",
            )
        return self.empty_result(
            FetchStatus.UPSTREAM_ERROR,
            error_message=f"{label} returned HTTP {code}",
        )

    def _map_to_wearables(
        self, sleep_payload: list, ready_rows: dict
    ) -> pd.DataFrame:
        """Project Oura responses onto :data:`WEARABLES_EXTENDED_COLUMNS`.

        Oura reports sleep durations in **seconds** and contributors as
        normalized 0-100 scores. We convert to hours for storage to match
        the existing wearables CSV convention.
        """
        out_rows = []
        for s in sleep_payload:
            day = s.get("day")
            if not day:
                continue
            contributors = s.get("contributors", {}) or {}
            ready_day = ready_rows.get(day, {}) or {}
            ready_contributors = ready_day.get("contributors", {}) or {}

            total_sleep_s = (
                s.get("total_sleep_duration")
                or contributors.get("total_sleep")
                or 0
            )
            deep_sleep_s = (
                s.get("deep_sleep_duration")
                or contributors.get("deep_sleep")
                or 0
            )
            rem_sleep_s = (
                s.get("rem_sleep_duration")
                or contributors.get("rem_sleep")
                or 0
            )

            out_rows.append(
                {
                    "date": day,
                    "resting_hr_bpm": (
                        ready_day.get("resting_heart_rate")
                        or ready_contributors.get("resting_heart_rate")
                    ),
                    "hrv_sdnn_ms": (
                        ready_day.get("hrv_balance")
                        or ready_contributors.get("hrv_balance")
                    ),
                    "sleep_duration_hrs": _seconds_to_hours(total_sleep_s),
                    "sleep_deep_hrs": _seconds_to_hours(deep_sleep_s),
                    "sleep_rem_hrs": _seconds_to_hours(rem_sleep_s),
                    "respiratory_rate_brpm": (
                        ready_day.get("respiratory_rate")
                        or ready_contributors.get("respiratory_rate")
                    ),
                    "source": self.name,
                }
            )

        # Always return the right column order, even for zero rows.
        if not out_rows:
            return pd.DataFrame(columns=self.columns)
        return pd.DataFrame(out_rows, columns=self.columns)


def _seconds_to_hours(value) -> Optional[float]:
    """Convert raw seconds to hours, preserving ``None`` for missing data.

    Oura reports either large integer seconds (durations) or 0-100 contributor
    scores. We treat anything <= 100 as a contributor score (already
    normalized) and pass it through unchanged; anything larger is seconds.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 100:
        # Contributor score path — pass through as-is, callers decide units.
        return v
    return round(v / 3600.0, 2)
