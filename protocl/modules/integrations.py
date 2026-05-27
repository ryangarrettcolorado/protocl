"""Integration catalog + inline SVG brand marks.

Defines every data source that feeds Protocōl — connected APIs, file-upload
parsers, and coming-soon placeholders. Renders crisp inline SVG marks that
match the dark/gold theme without requiring binary assets in the repo.

The catalog is consumed by `pages/19_integrations.py` to render a card grid
with status pills, freshness ("last sync") timestamps from import_log.csv,
and contextual action buttons.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ────────────────────────────────────────────────────────────────────────────
# SVG brand marks — 56x56 viewBox, monochrome where possible. Brand colors
# are kept only where they are essential to recognition (Strava orange,
# Apple Health red). Everything else uses gold (#FFB612) on transparent so
# cards blend into the dark theme.
# ────────────────────────────────────────────────────────────────────────────

GOLD = "#FFB612"
MUTED = "#6B6B70"

_SVG_BOX = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56" '
    'width="44" height="44" style="display:block">{inner}</svg>'
)


def _svg(inner: str) -> str:
    return _SVG_BOX.format(inner=inner)


# Connected APIs ─────────────────────────────────────────────────────────────
SVG_STRAVA = _svg(
    '<path d="M22 8 L8 36 H17 L22 26 L27 36 H36 L22 8 Z" fill="#FC4C02"/>'
    '<path d="M30 36 L36 47 L42 36 H37.5 L36 38.7 L34.5 36 Z" fill="#FC4C02" opacity="0.75"/>'
)

SVG_APPLE_HEALTH = _svg(
    '<path d="M28 46 C12 34 8 24 14 18 C19 13 25 16 28 21 '
    'C31 16 37 13 42 18 C48 24 44 34 28 46 Z" fill="#FF2D55"/>'
    '<path d="M21 28 H26 V23 H30 V28 H35 V32 H30 V37 H26 V32 H21 Z" fill="#fff"/>'
)

SVG_GITHUB = _svg(
    f'<path d="M28 6 C16 6 7 15 7 27 C7 37 13 45 22 48 C23 48 24 47 24 46 '
    f'V42 C18 43 17 39 17 39 C16 37 15 36 15 36 C13 35 15 35 15 35 '
    f'C17 35 18 37 18 37 C20 41 24 40 26 39 C26 37 27 36 28 36 '
    f'C23 35 18 33 18 25 C18 23 19 21 20 19 C20 19 19 17 20 14 '
    f'C20 14 22 13 26 16 C28 15 30 15 32 15 C34 15 36 15 38 16 '
    f'C42 13 44 14 44 14 C45 17 44 19 44 19 C45 21 46 23 46 25 '
    f'C46 33 41 35 36 36 C37 37 38 38 38 41 V46 C38 47 39 48 40 48 '
    f'C49 45 55 37 55 27 C55 15 46 6 28 6 Z" fill="{GOLD}"/>'
)

# Generic file-parsed sources ────────────────────────────────────────────────
SVG_BLOODWORK = _svg(
    f'<rect x="22" y="8" width="12" height="4" rx="1" fill="{GOLD}"/>'
    f'<path d="M23 12 V40 C23 44 26 47 28 47 C30 47 33 44 33 40 V12" '
    f'fill="none" stroke="{GOLD}" stroke-width="2.5"/>'
    f'<path d="M23 28 V40 C23 44 26 47 28 47 C30 47 33 44 33 40 V28 Z" '
    f'fill="{GOLD}" opacity="0.55"/>'
)

SVG_BODYCOMP = _svg(
    f'<rect x="8" y="14" width="40" height="34" rx="4" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.5"/>'
    f'<circle cx="28" cy="26" r="6" fill="none" stroke="{GOLD}" stroke-width="2.5"/>'
    f'<path d="M28 22 V26 L31 28" stroke="{GOLD}" stroke-width="2" '
    f'stroke-linecap="round" fill="none"/>'
    f'<rect x="22" y="40" width="12" height="2.5" rx="1" fill="{GOLD}"/>'
)

SVG_GPX = _svg(
    f'<path d="M6 44 L18 24 L26 34 L36 16 L50 44 Z" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.5" stroke-linejoin="round"/>'
    f'<path d="M14 30 L22 30" stroke="{GOLD}" stroke-width="2" opacity="0.6"/>'
    f'<circle cx="36" cy="16" r="2.5" fill="{GOLD}"/>'
)

SVG_ECG = _svg(
    f'<path d="M4 28 H16 L20 18 L26 38 L32 14 L38 32 L42 28 H52" '
    f'fill="none" stroke="{GOLD}" stroke-width="2.5" stroke-linejoin="round" '
    f'stroke-linecap="round"/>'
)

SVG_PROTOCOL = _svg(
    f'<rect x="14" y="8" width="28" height="40" rx="3" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.5"/>'
    f'<path d="M20 18 H36 M20 26 H36 M20 34 H30" stroke="{GOLD}" '
    f'stroke-width="2" stroke-linecap="round"/>'
    f'<circle cx="38" cy="40" r="6" fill="#0E0E10" stroke="{GOLD}" stroke-width="2"/>'
    f'<path d="M35 40 L37.5 42.5 L41 38.5" stroke="{GOLD}" stroke-width="2" '
    f'fill="none" stroke-linecap="round"/>'
)

SVG_MANUAL = _svg(
    f'<path d="M10 42 L34 18 L40 24 L16 48 L8 50 Z" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.5" stroke-linejoin="round"/>'
    f'<path d="M30 22 L36 28" stroke="{GOLD}" stroke-width="2.5"/>'
)

# Coming-soon placeholders ───────────────────────────────────────────────────
SVG_CGM = _svg(
    f'<circle cx="28" cy="28" r="14" fill="none" stroke="{MUTED}" stroke-width="2.5"/>'
    f'<circle cx="28" cy="28" r="5" fill="{MUTED}"/>'
    f'<path d="M28 8 V14 M28 42 V48 M8 28 H14 M42 28 H48" stroke="{MUTED}" '
    f'stroke-width="2.5" stroke-linecap="round"/>'
)

SVG_FULLSCRIPT = _svg(
    f'<path d="M18 10 L18 46 C18 48 19 50 22 50 H38 V42 H26 V36 H36 V30 H26 V18 H38 V10 Z" '
    f'fill="{MUTED}"/>'
)

SVG_OTHER_WEARABLE = _svg(
    f'<rect x="18" y="6" width="20" height="8" rx="2" fill="{MUTED}"/>'
    f'<rect x="14" y="14" width="28" height="28" rx="6" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.5"/>'
    f'<rect x="18" y="42" width="20" height="8" rx="2" fill="{MUTED}"/>'
    f'<circle cx="28" cy="28" r="6" fill="none" stroke="{MUTED}" stroke-width="2"/>'
)

SVG_SMART_SCALE = _svg(
    f'<rect x="6" y="20" width="44" height="22" rx="3" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.5"/>'
    f'<rect x="20" y="26" width="16" height="6" rx="1" fill="{MUTED}"/>'
    f'<path d="M14 42 V46 M42 42 V46" stroke="{MUTED}" stroke-width="2.5" '
    f'stroke-linecap="round"/>'
)

SVG_DEXA = _svg(
    f'<rect x="10" y="14" width="36" height="28" rx="3" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.5"/>'
    f'<circle cx="22" cy="24" r="2" fill="{MUTED}"/>'
    f'<path d="M26 22 C28 30 32 30 34 22" fill="none" stroke="{MUTED}" stroke-width="2"/>'
    f'<path d="M16 36 H40" stroke="{MUTED}" stroke-width="2" opacity="0.5"/>'
)


# ────────────────────────────────────────────────────────────────────────────
# Catalog
# ────────────────────────────────────────────────────────────────────────────

Status = Literal["connected", "file_based", "coming_soon"]
ConnectionType = Literal["oauth_api", "connector", "file_upload", "coming_soon"]


@dataclass
class Integration:
    key: str
    name: str
    category: str                  # "Lab" / "Wearable" / "Activity" / "Body Comp" / etc.
    status: Status
    connection_type: ConnectionType
    svg: str
    description: str
    source_types: list[str] = field(default_factory=list)   # rows in import_log.csv
    feed_label: str | None = None                            # for freshness lookup
    action_label: str = ""
    action_hint: str = ""


CATALOG: list[Integration] = [
    # ── Connected via API ────────────────────────────────────────────────
    Integration(
        key="strava",
        name="Strava",
        category="Activity",
        status="connected",
        connection_type="oauth_api",
        svg=SVG_STRAVA,
        description="Cycling & MTB rides with GPS, power and segment data. "
                    "Synced daily at 7:00 AM MDT.",
        source_types=["strava_api"],
        feed_label="Strava",
        action_label="Disconnect",
        action_hint="Pauses the daily cron and removes API access.",
    ),
    Integration(
        key="apple_health",
        name="Apple Health",
        category="Wearable",
        status="connected",
        connection_type="connector",
        svg=SVG_APPLE_HEALTH,
        description="Heart rate, HRV, sleep, steps and ECG from Apple Watch. "
                    "Backfills HR onto cycling rides.",
        source_types=["apple_healthkit_connector", "apple_health_ecg", "apple_health_gpx"],
        feed_label="Wearables",
        action_label="Disconnect",
        action_hint="Stops HealthKit sync via the connector.",
    ),
    Integration(
        key="github",
        name="GitHub",
        category="Code",
        status="connected",
        connection_type="connector",
        svg=SVG_GITHUB,
        description="Source of truth for this repo. Daily sync commits training "
                    "data updates back to main.",
        source_types=[],
        feed_label=None,
        action_label="Manage",
        action_hint="Open the connector settings.",
    ),

    # ── File-uploaded / parsed sources ───────────────────────────────────
    Integration(
        key="bloodwork",
        name="Bloodwork",
        category="Lab",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_BLOODWORK,
        description="LabCorp / Quest panels uploaded as PDF and parsed into "
                    "individual biomarker rows.",
        source_types=["bloodwork_pdf"],
        feed_label="Bloodwork",
        action_label="Upload PDF",
        action_hint="Goes to the Imports page.",
    ),
    Integration(
        key="inbody",
        name="InBody",
        category="Body Comp",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_BODYCOMP,
        description="Body composition exports from InBody scans — fat mass, "
                    "skeletal muscle, segmental water.",
        source_types=["inbody_csv"],
        feed_label="Body Comp",
        action_label="Upload CSV",
        action_hint="Goes to the Imports page.",
    ),
    Integration(
        key="gpx",
        name="GPX Routes",
        category="Activity",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_GPX,
        description="GPX files exported from Apple Health or bike computers. "
                    "Strava is now the primary source for new rides.",
        source_types=["training_gpx", "apple_health_gpx"],
        feed_label="Training",
        action_label="Upload GPX",
        action_hint="Adds rides not captured by Strava.",
    ),
    Integration(
        key="ecg",
        name="ECG",
        category="Wearable",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_ECG,
        description="Single-lead ECG strips from Apple Watch. Stored as "
                    "context notes with rhythm + average HR.",
        source_types=["apple_health_ecg"],
        feed_label="ECG",
        action_label="Upload ECG",
        action_hint="PDF export from Health app.",
    ),
    Integration(
        key="protocol",
        name="Protocol",
        category="Protocol",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_PROTOCOL,
        description="Weekly peptide & supplement protocol — markdown file "
                    "parsed into structured dose rows.",
        source_types=["protocol_md"],
        feed_label="Protocol",
        action_label="Upload MD",
        action_hint="Goes to the Imports page.",
    ),
    Integration(
        key="daily_log",
        name="Daily Log",
        category="Manual",
        status="file_based",
        connection_type="file_upload",
        svg=SVG_MANUAL,
        description="Manual daily entries — subjective sleep, mood, soreness, "
                    "and any notes that don't come from a device.",
        source_types=["manual_entry"],
        feed_label="Daily Log",
        action_label="Add entry",
        action_hint="Quick-add on the Home page.",
    ),

    # ── Coming soon ──────────────────────────────────────────────────────
    Integration(
        key="cgm",
        name="CGM (Dexcom / Libre)",
        category="Lab",
        status="coming_soon",
        connection_type="coming_soon",
        svg=SVG_CGM,
        description="Continuous glucose monitoring — 5-minute glucose, daily "
                    "mean, time-in-range and post-prandial spikes.",
        action_label="Notify me",
    ),
    Integration(
        key="fullscript",
        name="Fullscript",
        category="Supplements",
        status="coming_soon",
        connection_type="coming_soon",
        svg=SVG_FULLSCRIPT,
        description="Pull dispensary orders & active prescriptions so the "
                    "Protocol page auto-updates when a script changes.",
        action_label="Notify me",
    ),
    Integration(
        key="other_wearable",
        name="Whoop / Oura / Garmin",
        category="Wearable",
        status="coming_soon",
        connection_type="coming_soon",
        svg=SVG_OTHER_WEARABLE,
        description="Secondary wearables for redundant sleep, HRV and recovery "
                    "scoring — useful when the Apple Watch is on a charger.",
        action_label="Notify me",
    ),
    Integration(
        key="smart_scale",
        name="Smart Scale (Withings / Eufy)",
        category="Body Comp",
        status="coming_soon",
        connection_type="coming_soon",
        svg=SVG_SMART_SCALE,
        description="Daily weight and bio-impedance trends without manual "
                    "logging. Bridges the gap between monthly InBody scans.",
        action_label="Notify me",
    ),
    Integration(
        key="dexa",
        name="DEXA / BodPod",
        category="Body Comp",
        status="coming_soon",
        connection_type="coming_soon",
        svg=SVG_DEXA,
        description="Gold-standard body composition (regional bone density, "
                    "visceral fat, lean mass) for periodic recalibration.",
        action_label="Notify me",
    ),
]


def by_status(status: Status) -> list[Integration]:
    return [i for i in CATALOG if i.status == status]
