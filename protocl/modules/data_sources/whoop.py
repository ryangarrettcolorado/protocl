"""WHOOP Developer API — concrete :class:`OAuth2DataSource` implementation.

Why Whoop second
----------------

Whoop's API uses standard **OAuth 2.0 with refresh tokens** — the canonical
flow for every wearable platform that isn't Oura. Implementing Whoop validates
the :class:`OAuth2DataSource` scaffolding in :mod:`base` and gives Protocōl
direct access to WHOOP's three core data pillars: **Strain, Recovery, Sleep**.

Endpoints used
--------------

- ``GET /developer/v1/recovery`` — recovery score, HRV (rMSSD), resting HR
- ``GET /developer/v1/cycle`` — daily cycle strain + average HR
- ``GET /developer/v1/activity/sleep`` — sleep duration, stages, performance %

We merge these by cycle date and emit one row per calendar date in the
canonical extended wearables schema (see
:data:`base.WEARABLES_EXTENDED_COLUMNS`).

OAuth setup
-----------

Whoop OAuth is browser-based authorization-code flow. The operator runs the
flow **once** through Whoop's developer dashboard at developer.whoop.com to
mint a long-lived refresh token, then stores three secrets:

- ``WHOOP_CLIENT_ID``
- ``WHOOP_CLIENT_SECRET``
- ``WHOOP_REFRESH_TOKEN``

The refresh token is exchanged for a short-lived (1 hour) access token on
every sync run. Token caching is handled by :class:`OAuth2DataSource` —
this module only declares Whoop-specific config and implements the mapper.

Required scopes (declared in :attr:`token_scope`):

    offline
    read:recovery
    read:sleep
    read:cycles

The ``offline`` scope is what makes refresh tokens possible — without it,
Whoop returns access-token-only responses that expire after 1 hour with no
way to renew.

Approval gate
-------------

Whoop apps can be used immediately by up to **10 WHOOP members** without
review. Going beyond 10 requires submitting the app for Whoop's approval
process — privacy policy URL, design guidelines compliance, one verified
end-to-end integration. Typical turnaround is days to a week.

For Protocōl's 5-tester beta, this is non-blocking.
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


_API_BASE = "https://api.prod.whoop.com/developer/v1"


class WhoopDataSource(OAuth2DataSource):
    """Concrete :class:`DataSource` for WHOOP Developer API v1."""

    name = "whoop"
    display_name = "WHOOP"
    canonical_schema = "wearables"
    columns = WEARABLES_EXTENDED_COLUMNS

    # OAuth2DataSource contract
    secret_keys = ("WHOOP_CLIENT_ID", "WHOOP_CLIENT_SECRET", "WHOOP_REFRESH_TOKEN")
    token_url = "https://api.prod.whoop.com/oauth/oauth2/token"
    token_scope = "offline read:recovery read:sleep read:cycles"
    live_env_var = "WHOOP_LIVE"

    # ── data retrieval ───────────────────────────────────────────────────

    def fetch_window(self, start: date, end: date) -> FetchResult:
        if not self.is_configured():
            return self.empty_result(FetchStatus.NOT_CONFIGURED)
        if not self.is_live():
            return self.empty_result(FetchStatus.NOT_LIVE)

        # Whoop uses ISO-8601 timestamps in start/end query params, not just dates.
        params = {
            "start": f"{start.isoformat()}T00:00:00.000Z",
            "end": f"{end.isoformat()}T23:59:59.999Z",
            "limit": 25,
        }

        # ── Recovery endpoint ──────────────────────────────────────────
        recovery_response = self._authed_get(
            f"{_API_BASE}/recovery", params=params, label="recovery"
        )
        if isinstance(recovery_response, FetchResult):
            return recovery_response

        # ── Sleep endpoint ─────────────────────────────────────────────
        sleep_response = self._authed_get(
            f"{_API_BASE}/activity/sleep", params=params, label="sleep"
        )
        sleep_records: list = []
        if not isinstance(sleep_response, FetchResult):
            sleep_records = self._safe_records(sleep_response)
        # Sleep failure is non-fatal — we emit recovery-only rows.

        # ── Cycle endpoint (for resting HR backup + strain context) ───
        cycle_response = self._authed_get(
            f"{_API_BASE}/cycle", params=params, label="cycle"
        )
        cycle_records: list = []
        if not isinstance(cycle_response, FetchResult):
            cycle_records = self._safe_records(cycle_response)
        # Cycle failure is also non-fatal.

        recovery_records = self._safe_records(recovery_response)
        frame = self._map_to_wearables(
            recovery_records, sleep_records, cycle_records
        )
        return FetchResult(
            status=FetchStatus.OK,
            frame=frame,
            records_fetched=len(frame),
            source_name=self.name,
        )

    # ── internals ────────────────────────────────────────────────────────

    @staticmethod
    def _safe_records(response) -> list:
        """Defensively extract ``records`` array from a Whoop response."""
        try:
            body = response.json() or {}
        except Exception:
            return []
        records = body.get("records")
        return records if isinstance(records, list) else []

    def _map_to_wearables(
        self,
        recovery_records: list,
        sleep_records: list,
        cycle_records: list,
    ) -> pd.DataFrame:
        """Project Whoop responses onto :data:`WEARABLES_EXTENDED_COLUMNS`.

        Whoop reports durations in **milliseconds** and HRV in milliseconds
        (rMSSD). We convert sleep durations to hours; HRV passes through as
        milliseconds to match the ``hrv_sdnn_ms`` column name (note: Whoop
        reports rMSSD, not SDNN — same units, different metric, callers
        should interpret accordingly).
        """
        # Index sleep + cycle by their date for fast lookup.
        sleep_by_date = self._index_by_date(sleep_records)
        cycle_by_date = self._index_by_date(cycle_records)

        out_rows = []
        for rec in recovery_records:
            day = self._extract_date(rec)
            if not day:
                continue
            score = rec.get("score") or {}
            sleep = sleep_by_date.get(day, {})
            cycle = cycle_by_date.get(day, {})

            sleep_score = sleep.get("score") or {}
            stage_summary = sleep_score.get("stage_summary") or {}

            out_rows.append(
                {
                    "date": day,
                    "resting_hr_bpm": (
                        score.get("resting_heart_rate")
                        or (cycle.get("score") or {}).get("average_heart_rate")
                    ),
                    "hrv_sdnn_ms": score.get("hrv_rmssd_milli"),
                    "sleep_duration_hrs": _ms_to_hours(
                        sleep_score.get("total_in_bed_time_milli")
                    ),
                    "sleep_deep_hrs": _ms_to_hours(
                        stage_summary.get("total_slow_wave_sleep_time_milli")
                    ),
                    "sleep_rem_hrs": _ms_to_hours(
                        stage_summary.get("total_rem_sleep_time_milli")
                    ),
                    "respiratory_rate_brpm": score.get("respiratory_rate"),
                    "source": self.name,
                }
            )

        if not out_rows:
            return pd.DataFrame(columns=self.columns)
        return pd.DataFrame(out_rows, columns=self.columns)

    @staticmethod
    def _extract_date(record: dict) -> Optional[str]:
        """Whoop records use ``created_at`` ISO-8601 timestamps. We anchor
        each record to its calendar date (UTC, since Whoop is UTC-native)."""
        ts = record.get("created_at") or record.get("start") or ""
        if isinstance(ts, str) and len(ts) >= 10:
            return ts[:10]
        return None

    @classmethod
    def _index_by_date(cls, records: list) -> dict:
        out: dict = {}
        for r in records:
            d = cls._extract_date(r)
            if d and d not in out:
                out[d] = r
        return out


def _ms_to_hours(value) -> Optional[float]:
    """Convert milliseconds to hours, preserving ``None`` for missing data."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return round(v / 3_600_000.0, 2)
