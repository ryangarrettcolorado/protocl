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

# Generic file-parsed sources — each mark mimics the real-world device or
# document the data comes from.
# ────────────────────────────────────────────────────────────────────────────

# Bloodwork — Vacutainer blood-collection tube with red/gold stopper,
# label band, and blood fill in the lower portion. Reads as a LabCorp draw.
SVG_BLOODWORK = _svg(
    # Stopper cap (lavender/gold tone on real tubes)
    f'<rect x="21" y="6" width="14" height="6" rx="1.5" fill="{GOLD}"/>'
    f'<rect x="21" y="10" width="14" height="2" fill="{GOLD}" opacity="0.7"/>'
    # Tube outline (rounded bottom)
    f'<path d="M22 12 V42 C22 46 25 50 28 50 C31 50 34 46 34 42 V12 Z" '
    f'fill="none" stroke="{GOLD}" stroke-width="2.2"/>'
    # Blood fill in lower portion
    f'<path d="M22 32 V42 C22 46 25 50 28 50 C31 50 34 46 34 42 V32 Z" '
    f'fill="#C8102E" opacity="0.85"/>'
    # Liquid meniscus line
    f'<path d="M22 32 H34" stroke="#C8102E" stroke-width="1.5"/>'
    # White label band
    f'<rect x="22" y="18" width="12" height="7" fill="rgba(255,255,255,0.85)"/>'
    # Barcode lines on label
    f'<path d="M24 20 V23 M25.5 20 V23 M27 20 V23 M28.5 20 V23 '
    f'M30 20 V23 M31.5 20 V23" stroke="#0E0E10" stroke-width="0.6"/>'
)

# InBody — the actual machine silhouette: vertical column with handgrips,
# foot pads, and a display screen at the top.
SVG_BODYCOMP = _svg(
    # Base foot platform
    f'<rect x="10" y="44" width="36" height="6" rx="1" fill="none" '
    f'stroke="{GOLD}" stroke-width="2"/>'
    # Foot outlines on platform
    f'<ellipse cx="18" cy="47" rx="3" ry="1.5" fill="{GOLD}" opacity="0.45"/>'
    f'<ellipse cx="38" cy="47" rx="3" ry="1.5" fill="{GOLD}" opacity="0.45"/>'
    # Central column
    f'<rect x="24" y="14" width="8" height="30" fill="none" '
    f'stroke="{GOLD}" stroke-width="2"/>'
    # Display screen at top
    f'<rect x="16" y="6" width="24" height="12" rx="1.5" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.2"/>'
    f'<path d="M20 11 H32 M20 14 H28" stroke="{GOLD}" stroke-width="1.5" '
    f'opacity="0.8"/>'
    # Handgrip arms extending sideways
    f'<path d="M24 26 H14 M32 26 H42" stroke="{GOLD}" stroke-width="2" '
    f'stroke-linecap="round"/>'
    f'<circle cx="13" cy="26" r="2" fill="{GOLD}"/>'
    f'<circle cx="43" cy="26" r="2" fill="{GOLD}"/>'
)

# GPX — map pin with route trace (winding GPS path beneath the pin).
SVG_GPX = _svg(
    # Winding route trace at the bottom
    f'<path d="M6 46 C12 46 14 38 20 38 C26 38 28 44 34 44 '
    f'C40 44 42 36 50 36" fill="none" stroke="{GOLD}" '
    f'stroke-width="2" stroke-linecap="round" stroke-dasharray="1 3" '
    f'opacity="0.7"/>'
    # Map pin teardrop
    f'<path d="M28 6 C20 6 14 12 14 20 C14 28 22 36 28 44 '
    f'C34 36 42 28 42 20 C42 12 36 6 28 6 Z" fill="{GOLD}"/>'
    # Pin hole (dark center)
    f'<circle cx="28" cy="20" r="4.5" fill="#0E0E10"/>'
)

# ECG — Apple Watch silhouette with an ECG trace running across the face.
SVG_ECG = _svg(
    # Watch lugs (top + bottom)
    f'<rect x="19" y="4" width="18" height="6" rx="1.5" fill="{GOLD}" opacity="0.55"/>'
    f'<rect x="19" y="46" width="18" height="6" rx="1.5" fill="{GOLD}" opacity="0.55"/>'
    # Watch case
    f'<rect x="14" y="10" width="28" height="36" rx="6" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.4"/>'
    # Digital crown nub on right side
    f'<rect x="42" y="22" width="2.5" height="5" rx="0.5" fill="{GOLD}"/>'
    # ECG trace on the face
    f'<path d="M17 28 H22 L24 24 L26 32 L28 18 L30 36 L32 26 H39" '
    f'fill="none" stroke="{GOLD}" stroke-width="1.8" stroke-linejoin="round" '
    f'stroke-linecap="round"/>'
)

# Protocol — pill bottle with cap, prescription label, and visible pills.
SVG_PROTOCOL = _svg(
    # Cap
    f'<rect x="18" y="6" width="20" height="6" rx="1.5" fill="{GOLD}"/>'
    f'<rect x="20" y="4" width="16" height="3" rx="1" fill="{GOLD}" opacity="0.7"/>'
    # Bottle body
    f'<rect x="16" y="12" width="24" height="38" rx="3" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.2"/>'
    # Label background
    f'<rect x="18" y="18" width="20" height="14" fill="rgba(255,255,255,0.08)"/>'
    # Rx symbol on label
    f'<text x="21" y="29" font-family="Georgia, serif" font-size="11" '
    f'font-weight="700" fill="{GOLD}">℞</text>'
    # Label text lines
    f'<path d="M28 24 H36 M28 27 H34" stroke="{GOLD}" stroke-width="1" '
    f'opacity="0.7"/>'
    # Pills/capsules at the bottom of the bottle
    f'<rect x="20" y="38" width="6" height="3" rx="1.5" fill="{GOLD}" opacity="0.85"/>'
    f'<rect x="28" y="40" width="6" height="3" rx="1.5" fill="{GOLD}" opacity="0.85"/>'
    f'<rect x="22" y="44" width="6" height="3" rx="1.5" fill="{GOLD}" opacity="0.85"/>'
    f'<rect x="30" y="45" width="6" height="3" rx="1.5" fill="{GOLD}" opacity="0.85"/>'
)

# Daily Log — spiral-bound notebook with ruled lines and a check.
SVG_MANUAL = _svg(
    # Spiral binding rings down the left edge
    f'<circle cx="12" cy="12" r="1.8" fill="none" stroke="{GOLD}" stroke-width="1.5"/>'
    f'<circle cx="12" cy="22" r="1.8" fill="none" stroke="{GOLD}" stroke-width="1.5"/>'
    f'<circle cx="12" cy="32" r="1.8" fill="none" stroke="{GOLD}" stroke-width="1.5"/>'
    f'<circle cx="12" cy="42" r="1.8" fill="none" stroke="{GOLD}" stroke-width="1.5"/>'
    # Notebook page
    f'<rect x="16" y="6" width="32" height="44" rx="2" fill="none" '
    f'stroke="{GOLD}" stroke-width="2.2"/>'
    # Top header bar (date line)
    f'<rect x="20" y="11" width="20" height="2.5" rx="0.5" fill="{GOLD}" opacity="0.55"/>'
    # Ruled lines
    f'<path d="M20 20 H44 M20 26 H40 M20 32 H42 M20 38 H38" '
    f'stroke="{GOLD}" stroke-width="1.2" opacity="0.65"/>'
    # Checkmark on last line
    f'<path d="M22 44 L24 46 L28 42" stroke="{GOLD}" stroke-width="2" '
    f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
)

# Coming-soon placeholders — also shaped like the actual hardware so users
# recognize them at a glance. Muted gray to signal not-yet-available.
# ────────────────────────────────────────────────────────────────────────────

# CGM — adhesive sensor patch with a circular transmitter dome (Dexcom G7
# / Libre 3 silhouette: round disc on an oval adhesive base).
SVG_CGM = _svg(
    # Adhesive oval base (skin patch)
    f'<ellipse cx="28" cy="30" rx="22" ry="10" fill="none" '
    f'stroke="{MUTED}" stroke-width="2" stroke-dasharray="2 2"/>'
    # Transmitter dome (the circular puck)
    f'<circle cx="28" cy="28" r="11" fill="none" stroke="{MUTED}" stroke-width="2.5"/>'
    f'<circle cx="28" cy="28" r="7" fill="{MUTED}" opacity="0.4"/>'
    # Sensor indicator (center)
    f'<circle cx="28" cy="28" r="2.5" fill="{MUTED}"/>'
    # Wireless signal arcs above
    f'<path d="M22 14 Q28 10 34 14" fill="none" stroke="{MUTED}" '
    f'stroke-width="1.8" stroke-linecap="round" opacity="0.75"/>'
    f'<path d="M19 9 Q28 3 37 9" fill="none" stroke="{MUTED}" '
    f'stroke-width="1.8" stroke-linecap="round" opacity="0.5"/>'
)

# Fullscript — pharmacy prescription pad with Rx mark and signature line.
SVG_FULLSCRIPT = _svg(
    # Pad outline with torn-top stub
    f'<path d="M12 8 L44 8 L44 50 L12 50 Z" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.2"/>'
    # Tear perforations at top
    f'<path d="M14 12 H42" stroke="{MUTED}" stroke-width="1" '
    f'stroke-dasharray="2 2"/>'
    # Rx symbol
    f'<text x="17" y="30" font-family="Georgia, serif" font-size="14" '
    f'font-weight="700" fill="{MUTED}">℞</text>'
    # Prescription detail lines
    f'<path d="M28 22 H40 M28 26 H38 M16 36 H40 M16 40 H34" '
    f'stroke="{MUTED}" stroke-width="1.3" opacity="0.75"/>'
    # Signature line + scribble at bottom
    f'<path d="M16 46 H40" stroke="{MUTED}" stroke-width="1" opacity="0.5"/>'
    f'<path d="M28 45 C30 43 32 47 34 45" fill="none" stroke="{MUTED}" '
    f'stroke-width="1.4" stroke-linecap="round"/>'
)

# Other Wearable — Whoop-style fitness strap (no screen, just a band
# with a sensor module) to distinguish from the Apple Watch (ECG icon).
SVG_OTHER_WEARABLE = _svg(
    # Upper strap
    f'<path d="M14 6 L22 6 L24 22 L32 22 L34 6 L42 6" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.2" stroke-linejoin="round"/>'
    # Sensor module (rounded rectangle in the center)
    f'<rect x="20" y="22" width="16" height="12" rx="3" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.2"/>'
    # Optical heart-rate LEDs on the underside
    f'<circle cx="25" cy="28" r="1.5" fill="{MUTED}"/>'
    f'<circle cx="31" cy="28" r="1.5" fill="{MUTED}"/>'
    # Lower strap
    f'<path d="M14 50 L22 50 L24 34 L32 34 L34 50 L42 50" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.2" stroke-linejoin="round"/>'
)

# Smart Scale — top-down view with foot outlines and a digital readout.
SVG_SMART_SCALE = _svg(
    # Scale platform (rounded square top-down)
    f'<rect x="6" y="8" width="44" height="40" rx="6" fill="none" '
    f'stroke="{MUTED}" stroke-width="2.4"/>'
    # Foot outlines (top-down silhouettes)
    f'<ellipse cx="18" cy="22" rx="4" ry="6" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="15" cy="15" r="1.2" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="17" cy="14" r="1.1" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="19" cy="14" r="1" fill="{MUTED}" opacity="0.45"/>'
    f'<ellipse cx="38" cy="22" rx="4" ry="6" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="35" cy="15" r="1" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="37" cy="14" r="1.1" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="39" cy="14" r="1.2" fill="{MUTED}" opacity="0.45"/>'
    f'<circle cx="41" cy="15" r="1" fill="{MUTED}" opacity="0.45"/>'
    # Digital display readout
    f'<rect x="18" y="36" width="20" height="8" rx="1.5" fill="{MUTED}" opacity="0.55"/>'
    f'<path d="M22 40 H26 M28 40 H30 M32 40 H36" stroke="#0E0E10" '
    f'stroke-width="1.5" stroke-linecap="round"/>'
)

# DEXA — overhead scanner gantry/C-arm above a patient table.
SVG_DEXA = _svg(
    # Scanner arm (vertical post + horizontal beam above table)
    f'<rect x="6" y="6" width="4" height="32" rx="1" fill="{MUTED}"/>'
    f'<rect x="6" y="6" width="36" height="4" rx="1" fill="{MUTED}"/>'
    # Scan head hanging from the beam
    f'<rect x="34" y="10" width="10" height="8" rx="1.5" fill="{MUTED}"/>'
    f'<path d="M39 18 V24" stroke="{MUTED}" stroke-width="2"/>'
    # Scan beam lines (energy down to body)
    f'<path d="M36 18 V32 M39 18 V36 M42 18 V32" stroke="{MUTED}" '
    f'stroke-width="1" stroke-dasharray="1 2" opacity="0.6"/>'
    # Patient table
    f'<rect x="12" y="40" width="40" height="4" rx="1" fill="none" '
    f'stroke="{MUTED}" stroke-width="2"/>'
    # Body silhouette on table (head + torso)
    f'<circle cx="20" cy="36" r="2.5" fill="{MUTED}" opacity="0.55"/>'
    f'<rect x="24" y="34" width="22" height="5" rx="2" fill="{MUTED}" opacity="0.55"/>'
    # Table legs
    f'<path d="M16 44 V50 M48 44 V50" stroke="{MUTED}" stroke-width="2" '
    f'stroke-linecap="round"/>'
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
