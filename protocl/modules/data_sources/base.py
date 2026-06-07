"""DataSource — abstract contract for every external wearable/lab provider.

Design goals
------------

1. **Vendor-agnostic plumbing.** Pages, sync orchestrators, and tests interact
   with sources through this contract only — never directly against a vendor
   SDK. New providers (Whoop, Google Health, Garmin, Terra) drop in as new
   :class:`DataSource` subclasses without changes to ingestion plumbing.

2. **Presence-aware UI.** The catalog-driven biomarker/wearable renderer (v3.7)
   uses ``is_configured()`` to decide whether to show a panel or an empty-state
   CTA. A source that exists in the registry but has no credentials returns
   ``False`` from ``is_configured()`` — the page then renders an "Add
   credentials" affordance instead of an empty chart.

3. **Schema discipline.** Every source produces rows that conform to one of
   the canonical Protocōl schemas (``wearables``, ``training``, ``bloodwork``,
   ``cgm_readings``). The schema name is declared up front via
   :attr:`DataSource.canonical_schema` so the sync orchestrator can route the
   resulting frame to the right ``ProfileStorage`` write target.

4. **Failure isolation.** ``fetch_window()`` always returns a
   :class:`FetchResult` — never raises — so one provider's outage cannot abort
   a multi-source sync run. Errors are surfaced via :attr:`FetchResult.status`
   and :attr:`FetchResult.error_message` for the orchestrator's audit log.

This module intentionally has **zero runtime dependencies on Streamlit or
vendor SDKs** so it can be unit-tested in isolation.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Iterable, List, Optional

import pandas as pd


class FetchStatus(str, Enum):
    """Outcome of a single :meth:`DataSource.fetch_window` call."""

    OK = "ok"
    """Live fetch succeeded and the frame contains rows (possibly zero)."""

    NOT_CONFIGURED = "not_configured"
    """Credentials are missing. Caller should prompt the user to connect."""

    NOT_LIVE = "not_live"
    """Source is intentionally gated off (e.g. ``_LIVE = False``). Used during
    development to keep prod from hammering an unverified integration."""

    AUTH_ERROR = "auth_error"
    """Credentials present but rejected by the provider (401/403)."""

    RATE_LIMITED = "rate_limited"
    """Provider returned 429. Caller should back off, not retry immediately."""

    UPSTREAM_ERROR = "upstream_error"
    """Any other provider-side failure (5xx, malformed payload, timeout)."""


@dataclass
class FetchResult:
    """Uniform return shape from :meth:`DataSource.fetch_window`.

    ``frame`` is **always** a DataFrame matching the source's canonical
    schema — even on failure it's an empty frame with the right columns, so
    downstream code can ``pd.concat`` results without conditional branches.
    """

    status: FetchStatus
    frame: pd.DataFrame
    records_fetched: int = 0
    error_message: str = ""
    source_name: str = ""

    @property
    def ok(self) -> bool:
        return self.status is FetchStatus.OK

    @classmethod
    def empty(
        cls,
        status: FetchStatus,
        columns: Iterable[str],
        source_name: str,
        error_message: str = "",
    ) -> "FetchResult":
        """Build a no-rows result with the correct schema for the source."""
        return cls(
            status=status,
            frame=pd.DataFrame(columns=list(columns)),
            records_fetched=0,
            error_message=error_message,
            source_name=source_name,
        )


class ConfigError(RuntimeError):
    """Raised by :meth:`DataSource.validate_config` when credentials are
    structurally invalid (e.g. wrong length, missing required scope).

    Distinct from ``is_configured() is False`` which simply means *not yet
    connected* — :class:`ConfigError` means *connected but broken*.
    """


# ─────────────────────────────────────────────────────────────────────────────
# Canonical schemas — every DataSource maps its raw payload to one of these.
# These mirror the column lists already used by ProfileStorage seed templates
# (see protocl/storage.py SEED_FILES). Keeping the constants here lets tests
# assert schema conformance without importing the storage module.
# ─────────────────────────────────────────────────────────────────────────────

WEARABLES_COLUMNS = [
    "date",
    "sleep_score",
    "hrv_ms",
    "rhr_bpm",
    "steps",
    "notes",
]

# Extended wearables schema used by sources that report richer sleep + HR data
# than the legacy CSV. ``wearables.csv`` accepts the superset — extra columns
# are ignored by pages that only consume the legacy fields.
WEARABLES_EXTENDED_COLUMNS = [
    "date",
    "resting_hr_bpm",
    "hrv_sdnn_ms",
    "sleep_duration_hrs",
    "sleep_deep_hrs",
    "sleep_rem_hrs",
    "respiratory_rate_brpm",
    "source",
]

TRAINING_COLUMNS = [
    "date",
    "activity",
    "duration_min",
    "avg_hr",
    "notes",
]


# ─────────────────────────────────────────────────────────────────────────────
# Abstract base class
# ─────────────────────────────────────────────────────────────────────────────


class DataSource(ABC):
    """Abstract contract every concrete provider must implement.

    Subclasses declare four class-level attributes and implement three methods.
    The orchestrator (:mod:`protocl.modules.sync_orchestrator`) consumes only
    these — never anything vendor-specific.
    """

    #: Lowercase canonical name. Used as the registry key and the ``source``
    #: column value in produced frames. Must be stable across releases.
    name: str = ""

    #: Human-readable label shown in UI ("Oura Ring", "WHOOP", "Fitbit").
    display_name: str = ""

    #: Which canonical schema this source produces. The orchestrator uses this
    #: to route the resulting frame to the right ``ProfileStorage`` target.
    #: One of ``"wearables"``, ``"training"``, ``"bloodwork"``, ``"cgm"``.
    canonical_schema: str = ""

    #: Column list for the frame this source returns. Tests assert that
    #: every ``fetch_window`` result conforms to this exact column set.
    columns: List[str] = field(default_factory=list)

    # ── lifecycle ────────────────────────────────────────────────────────

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials are present (does *not* validate them)."""

    @abstractmethod
    def is_live(self) -> bool:
        """Return True if the source is enabled for live API calls.

        Development gate. Lets us ship a fully-tested integration that stays
        dormant until the operator explicitly flips it on.
        """

    def validate_config(self) -> None:
        """Optional: raise :class:`ConfigError` if credentials are malformed.

        Default implementation is a no-op so simple sources (PAT-based) need
        not override. OAuth sources should override to verify ``client_id``,
        ``client_secret``, and ``refresh_token`` are all present.
        """
        return None

    # ── data retrieval ───────────────────────────────────────────────────

    @abstractmethod
    def fetch_window(self, start: date, end: date) -> FetchResult:
        """Pull provider data for the inclusive date range ``[start, end]``.

        Must never raise. All failure modes are encoded in the returned
        :class:`FetchResult.status`. The returned frame's columns must equal
        :attr:`columns` exactly (use :meth:`FetchResult.empty` for failures).
        """

    # ── orchestrator support ─────────────────────────────────────────────

    def empty_result(
        self, status: FetchStatus, error_message: str = ""
    ) -> FetchResult:
        """Convenience: build an empty :class:`FetchResult` with this source's
        schema. Subclasses use this in their error branches."""
        return FetchResult.empty(
            status=status,
            columns=self.columns,
            source_name=self.name,
            error_message=error_message,
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"<{self.__class__.__name__} name={self.name!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# OAuth2DataSource — shared scaffolding for refresh-token-based sources.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class _CachedToken:
    """In-memory cache of a short-lived OAuth access token.

    Tokens are cached on the DataSource instance for the lifetime of the
    process so a single sync run that pulls multiple windows doesn't refresh
    on every call. ``expires_at_epoch`` is a UNIX timestamp; we treat the
    token as expired 60 seconds before its real expiry to avoid edge-case
    races where the request lands just as the token dies.
    """

    access_token: str
    expires_at_epoch: float


class OAuth2DataSource(DataSource):
    """Base class for sources that authenticate via OAuth 2.0 refresh tokens.

    Provides:

    - :meth:`is_configured` — checks for ``client_id``, ``client_secret``,
      and ``refresh_token`` secrets via the source's :attr:`secret_keys`
      class attribute.
    - :meth:`_refresh_access_token` — POSTs the refresh token to the provider's
      token endpoint, caches the response, and returns the new access token.
    - :meth:`_authed_get` — issues a GET with ``Authorization: Bearer …`` and
      classifies non-200 responses into :class:`FetchStatus`.

    Subclasses must:

    - Set :attr:`name`, :attr:`display_name`, :attr:`canonical_schema`,
      :attr:`columns` (inherited contract from :class:`DataSource`).
    - Set :attr:`secret_keys` to the tuple
      ``(client_id_key, client_secret_key, refresh_token_key)`` — the env-var /
      Streamlit secret names.
    - Set :attr:`token_url` to the provider's OAuth token endpoint.
    - Set :attr:`token_scope` to the space-separated scope string (some
      providers reject refresh requests without it).
    - Set :attr:`live_env_var` to the env var that gates live calls
      (e.g. ``"WHOOP_LIVE"``).
    - Implement :meth:`fetch_window` using :meth:`_authed_get`.
    """

    secret_keys: tuple = ()  # (client_id_key, client_secret_key, refresh_token_key)
    token_url: str = ""
    token_scope: str = ""
    live_env_var: str = ""

    # Treat token as expired this many seconds before real expiry.
    _TOKEN_EXPIRY_BUFFER_S = 60

    def __init__(self, *, request_fn=None, post_fn=None, clock_fn=None) -> None:
        self._request_fn = request_fn
        self._post_fn = post_fn
        self._clock_fn = clock_fn
        self._token_cache: Optional[_CachedToken] = None

    # ── configuration ───────────────────────────────────────────────────

    def is_configured(self) -> bool:
        if len(self.secret_keys) != 3:
            return False
        return all(bool(self._read_secret(key)) for key in self.secret_keys)

    def is_live(self) -> bool:
        if not self.live_env_var:
            return False
        value = (os.environ.get(self.live_env_var) or "").strip().lower()
        return value in {"1", "true", "yes", "on"}

    def validate_config(self) -> None:
        if len(self.secret_keys) != 3:
            raise ConfigError(
                f"{self.__class__.__name__}.secret_keys must be a 3-tuple"
            )
        missing = [k for k in self.secret_keys if not self._read_secret(k)]
        if missing and len(missing) < len(self.secret_keys):
            # Partially configured — that's broken (vs. fully absent which
            # is handled by is_configured()).
            raise ConfigError(
                f"OAuth credentials partially configured. Missing: {missing}"
            )

    # ── token management ────────────────────────────────────────────────

    def _refresh_access_token(self) -> Optional[FetchResult]:
        """Refresh the OAuth access token. Returns ``None`` on success (token
        is stored in :attr:`_token_cache`); returns a populated
        :class:`FetchResult` on failure so the caller can return it directly.
        """
        now = self._now()
        cache = self._token_cache
        if cache and cache.expires_at_epoch - self._TOKEN_EXPIRY_BUFFER_S > now:
            return None  # cached token still valid

        post = self._resolve_post_fn()
        if post is None:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message="`requests` library not installed",
            )

        client_id_key, client_secret_key, refresh_token_key = self.secret_keys
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self._read_secret(refresh_token_key),
            "client_id": self._read_secret(client_id_key),
            "client_secret": self._read_secret(client_secret_key),
        }
        if self.token_scope:
            payload["scope"] = self.token_scope

        try:
            response = post(self.token_url, data=payload, timeout=20)
        except Exception as exc:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"token refresh transport error: {exc}",
            )

        status_code = getattr(response, "status_code", None)
        if status_code != 200:
            return self.empty_result(
                FetchStatus.AUTH_ERROR,
                error_message=f"token refresh returned HTTP {status_code}",
            )

        try:
            body = response.json() or {}
        except Exception as exc:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"token refresh JSON decode failed: {exc}",
            )

        token = body.get("access_token")
        if not token:
            return self.empty_result(
                FetchStatus.AUTH_ERROR,
                error_message="token refresh response missing access_token",
            )

        expires_in = float(body.get("expires_in") or 3600)
        self._token_cache = _CachedToken(
            access_token=token,
            expires_at_epoch=now + expires_in,
        )
        return None

    # ── helpers ────────────────────────────────────────────────────────

    def _authed_get(
        self,
        url: str,
        params: Optional[dict] = None,
        label: str = "request",
    ):
        """Issue an authenticated GET. Returns either a response-like object
        or a :class:`FetchResult` describing the failure. Callers check
        ``isinstance(result, FetchResult)`` to branch.
        """
        refresh_failure = self._refresh_access_token()
        if refresh_failure is not None:
            return refresh_failure

        get = self._resolve_request_fn()
        if get is None:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message="`requests` library not installed",
            )

        cache = self._token_cache
        headers = {"Authorization": f"Bearer {cache.access_token}"}  # type: ignore[union-attr]
        try:
            response = get(url, headers=headers, params=params or {}, timeout=30)
        except Exception as exc:
            return self.empty_result(
                FetchStatus.UPSTREAM_ERROR,
                error_message=f"{label} transport error: {exc}",
            )

        code = getattr(response, "status_code", None)
        if code == 200:
            return response
        if code in (401, 403):
            # Token may have been revoked. Invalidate cache so the next call
            # forces a fresh refresh.
            self._token_cache = None
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

    # ── injection seams (overridable for tests) ─────────────────────────

    def _read_secret(self, key: str) -> Optional[str]:
        """Read a secret from Streamlit secrets, falling back to env var.

        Implemented as an instance method so test subclasses can stub the
        whole credential surface without monkeypatching Streamlit.
        """
        try:
            import streamlit as st  # type: ignore

            try:
                if key in st.secrets:  # type: ignore[operator]
                    return st.secrets[key]
            except Exception:
                pass
        except ImportError:
            pass
        return os.environ.get(key)

    def _now(self) -> float:
        if self._clock_fn is not None:
            return float(self._clock_fn())
        import time

        return time.time()

    def _resolve_request_fn(self):
        if self._request_fn is not None:
            return self._request_fn
        try:
            import requests  # noqa: WPS433

            return requests.get
        except ImportError:
            return None

    def _resolve_post_fn(self):
        if self._post_fn is not None:
            return self._post_fn
        try:
            import requests  # noqa: WPS433

            return requests.post
        except ImportError:
            return None
