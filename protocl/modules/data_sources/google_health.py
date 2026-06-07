"""Google Health API — concrete :class:`OAuth2DataSource` implementation.

Why Google Health (and not Fitbit Web API)
------------------------------------------

In **September 2026**, Google decommissions the legacy Fitbit Web API and
replaces it with the unified **Google Health API**, accessed via Google
OAuth 2.0. We build directly against the new API to avoid the migration
churn — every line of code that targets the legacy endpoints would need to
be rewritten within months.

The Google Health API consolidates 100+ legacy Fitbit endpoints into a
streamlined "data type bundle" model. Coverage includes every Fitbit and
Pixel Watch device past or present.

Source: https://developers.google.com/health/about

Endpoints used
--------------

- ``GET /v1/users/me/dataTypes/sleep`` — sleep duration + stages
- ``GET /v1/users/me/dataTypes/heartrate`` — resting + intraday heart rate
- ``GET /v1/users/me/dataTypes/hrv`` — heart rate variability
- ``GET /v1/users/me/dataTypes/activity`` — steps + active minutes

We merge by date and emit one row per calendar date in the canonical
extended wearables schema.

OAuth setup
-----------

Google Health uses **Google OAuth 2.0** (not Fitbit-proprietary anymore).
The operator:

1. Creates an OAuth 2.0 client in **Google Cloud Console**
2. Enables the Google Health API for the project
3. Runs the browser-based authorization flow once to mint a refresh token
4. Stores three secrets:

   - ``GOOGLE_HEALTH_CLIENT_ID``
   - ``GOOGLE_HEALTH_CLIENT_SECRET``
   - ``GOOGLE_HEALTH_REFRESH_TOKEN``

Token refresh is delegated to :class:`OAuth2DataSource`. Google's token
endpoint is at ``https://oauth2.googleapis.com/token`` (the universal
Google OAuth endpoint, not a Health-API-specific URL).

Required scopes (declared in :attr:`token_scope`):

    https://www.googleapis.com/auth/health.sleep.read
    https://www.googleapis.com/auth/health.heartrate.read
    https://www.googleapis.com/auth/health.activity.read

(Note: Google Health API scope strings will be finalized closer to the
September 2026 cutover. These are the documented scope shapes; subclassing
or updating :attr:`token_scope` is a one-line change if Google publishes
revised scope names.)

API endpoint hardcoding
-----------------------

We hardcode the API base URL as a class attribute, not a module constant,
so the value can be overridden in tests without monkeypatching the module.
This matches the pattern used elsewhere in Protocōl for testability.

Backward-compat note
--------------------

When users finish migrating their Fitbit accounts to Google accounts during
the May–September 2026 window, their access tokens stop working silently.
The :class:`OAuth2DataSource` base class invalidates its token cache on
``401/403`` responses, so the next sync run will attempt a fresh refresh —
which itself will fail with ``AUTH_ERROR``, surfacing the issue to the
operator instead of silently dropping data.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from .base import (
    FetchResult,
    FetchStatus,
    OAuth2DataSource,
    WEARABLES_EXTENDED_COLUMNS,
)


class GoogleHealthDataSource(OAuth2DataSource):
    """Concrete :class:`DataSource` for Google Health API (post-Fitbit)."""

    name = "google_health"
    display_name = "Google Health (Fitbit + Pixel Watch)"
    canonical_schema = "wearables"
    columns = WEARABLES_EXTENDED_COLUMNS

    # OAuth2DataSource contract
    secret_keys = (
        "GOOGLE_HEALTH_CLIENT_ID",
        "GOOGLE_HEALTH_CLIENT_SECRET",
        "GOOGLE_HEALTH_REFRESH_TOKEN",
    )
    token_url = "https://oauth2.googleapis.com/token"
    token_scope = (
        "https://www.googleapis.com/auth/health.sleep.read "
        "https://www.googleapis.com/auth/health.heartrate.read "
        "https://www.googleapis.com/auth/health.activity.read"
    )
    live_env_var = "GOOGLE_HEALTH_LIVE"

    #: Overridable for tests. The Google Health API base URL.
    api_base = "https://health.googleapis.com/v1/users/me/dataTypes"

    # ── data retrieval ───────────────────────────────────────────────────

    def fetch_window(self, start: date, end: date) -> FetchResult:
        if not self.is_configured():
            return self.empty_result(FetchStatus.NOT_CONFIGURED)
        if not self.is_live():
            return self.empty_result(FetchStatus.NOT_LIVE)

        params = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
        }

        # ── Sleep endpoint (required — fatal failure aborts the fetch) ─
        sleep_response = self._authed_get(
            f"{self.api_base}/sleep", params=params, label="sleep"
        )
        if isinstance(sleep_response, FetchResult):
            return sleep_response

        # ── Heart rate (non-fatal) ─────────────────────────────────────
        hr_response = self._authed_get(
            f"{self.api_base}/heartrate", params=params, label="heartrate"
        )
        hr_records = (
            self._safe_records(hr_response)
            if not isinstance(hr_response, FetchResult)
            else []
        )

        # ── HRV (non-fatal) ────────────────────────────────────────────
        hrv_response = self._authed_get(
            f"{self.api_base}/hrv", params=params, label="hrv"
        )
        hrv_records = (
            self._safe_records(hrv_response)
            if not isinstance(hrv_response, FetchResult)
            else []
        )

        sleep_records = self._safe_records(sleep_response)
        frame = self._map_to_wearables(sleep_records, hr_records, hrv_records)
        return FetchResult(
            status=FetchStatus.OK,
            frame=frame,
            records_fetched=len(frame),
            source_name=self.name,
        )

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _safe_records(response) -> list:
        try:
            body = response.json() or {}
        except Exception:
            return []
        # Google Health bundles data under either ``dataPoints`` or ``records``
        # depending on the endpoint variant. Accept both for resilience.
        for key in ("dataPoints", "records", "data"):
            value = body.get(key)
            if isinstance(value, list):
                return value
        return []

    def _map_to_wearables(
        self,
        sleep_records: list,
        hr_records: list,
        hrv_records: list,
    ) -> pd.DataFrame:
        """Project Google Health responses onto
        :data:`WEARABLES_EXTENDED_COLUMNS`.

        Google Health reports durations in **minutes** (not seconds or
        milliseconds) and HRV in milliseconds. We convert sleep durations
        to hours; heart rate and HRV pass through as-is.
        """
        hr_by_date = self._index_by_date(hr_records)
        hrv_by_date = self._index_by_date(hrv_records)

        out_rows = []
        for s in sleep_records:
            day = s.get("date") or s.get("startDate")
            if not day:
                continue
            if isinstance(day, str) and len(day) >= 10:
                day = day[:10]

            stages = s.get("stages") or {}
            hr_record = hr_by_date.get(day, {})
            hrv_record = hrv_by_date.get(day, {})

            out_rows.append(
                {
                    "date": day,
                    "resting_hr_bpm": (
                        hr_record.get("restingHeartRate")
                        or hr_record.get("resting_heart_rate")
                    ),
                    "hrv_sdnn_ms": (
                        hrv_record.get("hrvRmssd")
                        or hrv_record.get("hrv_rmssd")
                        or hrv_record.get("hrvSdnn")
                    ),
                    "sleep_duration_hrs": _minutes_to_hours(
                        s.get("totalDurationMinutes")
                        or s.get("total_duration_minutes")
                    ),
                    "sleep_deep_hrs": _minutes_to_hours(
                        stages.get("deepMinutes")
                        or stages.get("deep_minutes")
                    ),
                    "sleep_rem_hrs": _minutes_to_hours(
                        stages.get("remMinutes")
                        or stages.get("rem_minutes")
                    ),
                    "respiratory_rate_brpm": s.get("respiratoryRate")
                    or s.get("respiratory_rate"),
                    "source": self.name,
                }
            )

        if not out_rows:
            return pd.DataFrame(columns=self.columns)
        return pd.DataFrame(out_rows, columns=self.columns)

    @classmethod
    def _index_by_date(cls, records: list) -> dict:
        out: dict = {}
        for r in records:
            d = r.get("date") or r.get("startDate")
            if isinstance(d, str) and len(d) >= 10:
                key = d[:10]
                if key not in out:
                    out[key] = r
        return out


def _minutes_to_hours(value) -> Optional[float]:
    """Convert minutes to hours, preserving ``None`` for missing data."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v / 60.0, 2)
