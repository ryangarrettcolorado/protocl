"""v3.5 — in-app changelog parsing + unseen-version detection.

Parses ``CHANGELOG.md`` at the repo root into structured versions. "Latest"
is the first ``## v…`` heading (the file is maintained newest-first). Unseen
detection compares the per-user ``last_seen_changelog_version`` (in
``preferences.json`` via :mod:`user_prefs`) against the latest parsed version.

Format expected::

    # Changelog

    ## v3.6 — 2026-06-01
    ### Added
    - Page-view tracking

    ## v3.5 — 2026-05-31
    ### Added
    - Account deletion
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from modules import user_prefs
from storage import ProfileStorage


# CHANGELOG.md lives at the repo root: protocl/modules/ -> protocl/ -> repo root.
CHANGELOG_PATH = Path(__file__).resolve().parent.parent.parent / "CHANGELOG.md"

_VERSION_RE = re.compile(r"^##\s+(v[\w.]+)\s*(?:—|-|–)?\s*(.*)$")
_SECTION_RE = re.compile(r"^###\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")


@dataclass
class ChangelogVersion:
    version: str
    date: str = ""
    sections: dict[str, list[str]] = field(default_factory=dict)


def parse_changelog(path: Path | None = None) -> list[ChangelogVersion]:
    """Parse CHANGELOG.md into an ordered (newest-first) list of versions."""
    p = path or CHANGELOG_PATH
    if not p.exists():
        return []
    versions: list[ChangelogVersion] = []
    current: ChangelogVersion | None = None
    current_section: str | None = None
    for raw in p.read_text().splitlines():
        line = raw.rstrip()
        m = _VERSION_RE.match(line)
        if m:
            current = ChangelogVersion(version=m.group(1), date=m.group(2).strip())
            versions.append(current)
            current_section = None
            continue
        if current is None:
            continue
        ms = _SECTION_RE.match(line)
        if ms:
            current_section = ms.group(1).strip()
            current.sections.setdefault(current_section, [])
            continue
        mb = _BULLET_RE.match(line.strip())
        if mb and current_section is not None:
            current.sections[current_section].append(mb.group(1).strip())
    return versions


def latest_version(path: Path | None = None) -> str | None:
    versions = parse_changelog(path)
    return versions[0].version if versions else None


def has_unseen(store: ProfileStorage | None = None, path: Path | None = None) -> bool:
    """True if the latest changelog version is newer than what the user saw."""
    latest = latest_version(path)
    if latest is None:
        return False
    seen = user_prefs.get("last_seen_changelog_version", None, store)
    return seen != latest


def mark_seen(store: ProfileStorage | None = None, path: Path | None = None) -> None:
    """Record that the user has seen the latest version (called on page view)."""
    latest = latest_version(path)
    if latest is not None:
        user_prefs.set_value("last_seen_changelog_version", latest, store)


def banner_dismissed(version: str, store: ProfileStorage | None = None) -> bool:
    dismissed = user_prefs.get("changelog_banner_dismissed", [], store) or []
    return version in dismissed


def dismiss_banner(version: str, store: ProfileStorage | None = None) -> None:
    store = store or ProfileStorage()
    prefs = user_prefs.load(store)
    dismissed = list(prefs.get("changelog_banner_dismissed", []) or [])
    if version not in dismissed:
        dismissed.append(version)
    prefs["changelog_banner_dismissed"] = dismissed
    user_prefs.save(prefs, store)


def should_show_home_banner(store: ProfileStorage | None = None,
                            path: Path | None = None) -> bool:
    """Home banner shows once per unseen version (until dismissed)."""
    latest = latest_version(path)
    if latest is None:
        return False
    if not has_unseen(store, path):
        return False
    return not banner_dismissed(latest, store)
