"""Unified data-source abstraction layer (v3.8).

Every external wearable/lab provider implements the :class:`DataSource`
interface from :mod:`protocl.modules.data_sources.base`. Pages, sync
orchestrators, and tests interact with sources only through that contract —
never directly against vendor SDKs — so new providers can be added without
touching ingestion plumbing.

Concrete implementations live alongside this module:

- :mod:`protocl.modules.data_sources.oura` — Oura Cloud API v2 (PAT)
- :mod:`protocl.modules.data_sources.whoop` — Whoop Developer API (OAuth 2.0)
- :mod:`protocl.modules.data_sources.google_health` — Google Health API (post-Fitbit migration)

The :func:`registry` helper returns a name-keyed map of every concrete source
that imports cleanly, so the sync orchestrator can iterate without hard-coded
``if/elif`` chains.
"""
from __future__ import annotations

from typing import Dict

from .base import DataSource, FetchResult, FetchStatus, ConfigError


def registry() -> Dict[str, DataSource]:
    """Return all importable, concrete data sources keyed by canonical name.

    Sources that fail to import (missing optional deps) are silently omitted
    so the rest of the app keeps working. Sources that import but aren't
    configured (no credentials) are *included* — they answer ``is_configured()``
    with ``False`` so callers can render an "Add credentials" CTA.
    """
    sources: Dict[str, DataSource] = {}

    try:
        from .oura import OuraDataSource

        sources["oura"] = OuraDataSource()
    except Exception:
        pass

    try:
        from .whoop import WhoopDataSource

        sources["whoop"] = WhoopDataSource()
    except Exception:
        pass

    try:
        from .google_health import GoogleHealthDataSource

        sources["google_health"] = GoogleHealthDataSource()
    except Exception:
        pass

    return sources


__all__ = [
    "DataSource",
    "FetchResult",
    "FetchStatus",
    "ConfigError",
    "registry",
]
