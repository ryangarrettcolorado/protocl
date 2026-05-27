"""Data-freshness badges.

Reads `data/ryan/import_log.csv` and computes the latest import timestamp per
logical feed. Renders a compact horizontal strip of pills the user can scan in
under a second to know what's stale.
"""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import streamlit as st

from modules.theme import UI_VERSION, UI_BUILD_LABEL

LOG_PATH = Path(__file__).resolve().parents[1] / "data" / "ryan" / "import_log.csv"

# Map raw source_type values in import_log.csv -> human-readable feed names.
SOURCE_LABELS = {
    "bloodwork_pdf": "Bloodwork",
    "inbody_csv": "Body Comp",
    "protocol_md": "Protocol",
    "apple_health_ecg": "ECG",
    "training_gpx": "Training",
    "apple_healthkit_connector": "Wearables",
    "manual_entry": "Daily Log",
}

# Feed -> warning thresholds in days. Anything beyond `stale_after_days` shows
# the amber pill; anything beyond `very_stale_after_days` shows red.
THRESHOLDS = {
    "Bloodwork":  (120, 180),   # quarterly cadence
    "Body Comp":  (14, 30),     # roughly monthly
    "Protocol":   (45, 90),
    "ECG":        (90, 180),
    "Training":   (3, 7),
    "Wearables":  (2, 5),
    "Daily Log":  (2, 5),
}


def _read_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=["timestamp", "source_type", "filename",
                                       "rows_imported", "rows_skipped_duplicate",
                                       "errors", "imported_by"])
    df = pd.read_csv(LOG_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df.dropna(subset=["timestamp"])


def _latest_per_feed(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    out: dict[str, pd.Timestamp] = {}
    for source_type, label in SOURCE_LABELS.items():
        sub = df[df["source_type"] == source_type]
        if sub.empty:
            continue
        out[label] = sub["timestamp"].max()
    return out


def _humanize(ts: pd.Timestamp, now: datetime) -> tuple[str, str]:
    """Return (label, color). Color is one of: green / amber / red / muted."""
    if pd.isna(ts):
        return ("never", "muted")
    delta = now - ts.to_pydatetime().replace(tzinfo=now.tzinfo) if ts.tzinfo else now - ts.to_pydatetime()
    secs = delta.total_seconds()
    if secs < 60:
        return ("just now", "green")
    if secs < 3600:
        return (f"{int(secs/60)}m ago", "green")
    if secs < 86400:
        return (f"{int(secs/3600)}h ago", "green")
    days = int(secs / 86400)
    if days == 1:
        return ("1d ago", "green")
    return (f"{days}d ago", "")  # color resolved later via threshold


def _color_for(feed: str, days_old: int) -> str:
    if feed not in THRESHOLDS:
        return "muted"
    amber, red = THRESHOLDS[feed]
    if days_old >= red:
        return "red"
    if days_old >= amber:
        return "amber"
    return "green"


def render_freshness_strip(*, show_build: bool = True) -> None:
    """Render a single-row strip of pills above the page header."""
    df = _read_log()
    latest = _latest_per_feed(df)
    now = datetime.now()

    color_to_css = {
        "green": "background:rgba(63,191,127,0.15); color:#3FBF7F; border:1px solid rgba(63,191,127,0.35);",
        "amber": "background:rgba(255,182,18,0.15); color:#FFB612; border:1px solid rgba(255,182,18,0.40);",
        "red":   "background:rgba(255,90,90,0.15); color:#FF7373; border:1px solid rgba(255,90,90,0.40);",
        "muted": "background:rgba(255,255,255,0.04); color:#888; border:1px solid rgba(255,255,255,0.08);",
    }

    pills_html: list[str] = []
    for feed_label in SOURCE_LABELS.values():
        ts = latest.get(feed_label)
        if ts is None:
            color = "muted"
            text = "never"
        else:
            text, base_color = _humanize(ts, now)
            if base_color:
                color = base_color
            else:
                days = (now - ts.to_pydatetime()).days
                color = _color_for(feed_label, days)
        css = color_to_css.get(color, color_to_css["muted"])
        pills_html.append(
            f'<span style="display:inline-flex; align-items:center; gap:0.4rem; '
            f'padding:0.18rem 0.6rem; border-radius:999px; font-size:0.72rem; '
            f'font-weight:500; letter-spacing:0.02em; {css}">'
            f'<span style="opacity:0.8">{feed_label}</span>'
            f'<span style="font-variant-numeric:tabular-nums;">{text}</span>'
            f'</span>'
        )

    if show_build:
        pills_html.append(
            f'<span style="display:inline-flex; align-items:center; gap:0.4rem; '
            f'padding:0.18rem 0.6rem; border-radius:999px; font-size:0.7rem; '
            f'font-weight:500; letter-spacing:0.04em; '
            f'background:rgba(255,182,18,0.08); color:#FFB612; '
            f'border:1px solid rgba(255,182,18,0.25);" '
            f'title="{UI_BUILD_LABEL}">UI v{UI_VERSION}</span>'
        )

    strip = (
        '<div style="display:flex; flex-wrap:wrap; gap:0.4rem; '
        'margin:0.1rem 0 0.9rem 0;">'
        + "".join(pills_html) +
        '</div>'
    )
    st.markdown(strip, unsafe_allow_html=True)
