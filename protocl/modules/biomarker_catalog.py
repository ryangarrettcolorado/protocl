"""Biomarker catalog — single source of truth for all markers Protocōl can ingest.

This module is the canonical loader for ``config/biomarker_catalog.yaml``. It
exposes both the new tri-band classification API and a backwards-compatible
``reference_dict`` shape so legacy callers (``home_dashboard.py``,
``04_bloodwork.py``, etc.) continue to work without modification.

Design goals
------------
* **Catalog-driven**: adding a new marker is a YAML edit, not a code change.
* **Cross-lab aliasing**: every marker carries the LabCorp / Quest / Function
  synonyms in its aliases array; ingest fuzzy-matches against this map.
* **Presence-aware**: callers ask "which markers does *this user* have data for?"
  via :func:`present_markers` and only those render.
* **Backward compatible**: the legacy
  ``apob_mg_dl`` style canonical keys are preserved as a derived view so
  existing pages keep working during migration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except ImportError as exc:  # pragma: no cover - import error path
    raise ImportError(
        "PyYAML is required to load the biomarker catalog. "
        "Install with: pip install pyyaml"
    ) from exc


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Look first in the runtime config directory; fall back to a sibling reference
# directory for local development.
_CANDIDATE_PATHS = (
    Path(__file__).resolve().parents[2] / "config" / "biomarker_catalog.yaml",
    Path(__file__).resolve().parents[1] / "reference" / "biomarker_catalog.yaml",
    Path(__file__).resolve().parents[2] / "biomarker_catalog.yaml",
)


def _resolve_catalog_path(override: Path | str | None = None) -> Path:
    """Return the first catalog path that exists.

    Pass *override* in tests to point at a fixture file.
    """
    if override is not None:
        p = Path(override)
        if not p.exists():
            raise FileNotFoundError(f"Biomarker catalog override not found: {p}")
        return p
    for candidate in _CANDIDATE_PATHS:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "biomarker_catalog.yaml not found. Looked in: "
        + ", ".join(str(c) for c in _CANDIDATE_PATHS)
    )


# ---------------------------------------------------------------------------
# Enums & dataclasses
# ---------------------------------------------------------------------------


class Direction(str, Enum):
    """Which way 'better' points on the number line for a given marker."""

    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"
    MID_RANGE = "mid_range"
    BINARY_FLAG = "binary_flag"


class Status(str, Enum):
    """The four bands Protocōl renders for any single result."""

    OPTIMAL = "optimal"
    BORDERLINE = "borderline"
    OUT_OF_RANGE = "out_of_range"
    PRESENT = "present"  # for binary_flag markers
    ABSENT = "absent"  # for binary_flag markers
    UNKNOWN = "unknown"  # no data or no ranges defined


@dataclass(frozen=True)
class Ranges:
    """The tri-band reference range for a marker."""

    optimal_min: float | None = None
    optimal_max: float | None = None
    borderline_min: float | None = None
    borderline_max: float | None = None
    out_of_range_low_max: float | None = None
    out_of_range_high_min: float | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Ranges":
        d = d or {}
        return cls(
            optimal_min=d.get("optimal_min"),
            optimal_max=d.get("optimal_max"),
            borderline_min=d.get("borderline_min"),
            borderline_max=d.get("borderline_max"),
            out_of_range_low_max=d.get("out_of_range_low_max"),
            out_of_range_high_min=d.get("out_of_range_high_min"),
        )


@dataclass(frozen=True)
class Marker:
    """A single biomarker entry from the catalog."""

    canonical_key: str
    display_name: str
    category: str
    tier: int
    direction: Direction
    units: str | None
    aliases: tuple[str, ...]
    ranges: Ranges
    source_citation: str | None
    source_url: str | None
    notes: str

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Marker":
        return cls(
            canonical_key=d["canonical_key"],
            display_name=d["display_name"],
            category=d["category"],
            tier=int(d["tier"]),
            direction=Direction(d["direction"]),
            units=d.get("units"),
            aliases=tuple(d.get("aliases", []) or []),
            ranges=Ranges.from_dict(d.get("ranges", {})),
            source_citation=d.get("source_citation"),
            source_url=d.get("source_url"),
            notes=(d.get("notes") or "").strip(),
        )

    # -- legacy compatibility view ----------------------------------------
    def as_legacy_entry(self) -> dict[str, Any]:
        """Return a dict matching the legacy ``biomarker_reference.json`` shape.

        Used to keep ``home_dashboard.py``, ``04_bloodwork.py``, and other
        existing pages working without modification.
        """
        return {
            "panel": _category_to_legacy_panel(self.category),
            "unit": self.units or "",
            "optimal_low": self.ranges.optimal_min,
            "optimal_high": self.ranges.optimal_max,
            "lab_low": self.ranges.out_of_range_low_max,
            "lab_high": self.ranges.out_of_range_high_min,
            "tier": f"T{self.tier}",
            "source": self.source_citation,
            "source_url": self.source_url,
            "description": self.notes,
        }


# Map new catalog categories back onto legacy "panel" strings used by old pages.
_CATEGORY_TO_LEGACY_PANEL = {
    "lipids": "lipids",
    "metabolic": "glucose_insulin",
    "inflammation": "inflammation",
    "hormones": "hormones",
    "thyroid": "thyroid",
    "liver_kidney": "kidney",  # legacy split; pages handle both labels
    "vitamins": "vitamins_minerals",
    "cbc": "hematology",
    "urinalysis": "other",
}


def _category_to_legacy_panel(category: str) -> str:
    return _CATEGORY_TO_LEGACY_PANEL.get(category, "other")


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Catalog:
    """Parsed biomarker catalog. Immutable; safe to cache and share."""

    schema_version: int
    total_markers: int
    categories: tuple[dict[str, Any], ...]
    markers: tuple[Marker, ...]
    _by_key: dict[str, Marker] = field(default_factory=dict, repr=False)
    _by_alias: dict[str, Marker] = field(default_factory=dict, repr=False)

    # ---- lookups -----------------------------------------------------------

    def get(self, key_or_alias: str) -> Marker | None:
        """Resolve a canonical key OR an alias (case-insensitive) to a Marker."""
        if not key_or_alias:
            return None
        norm = _normalize_lookup(key_or_alias)
        return self._by_key.get(norm) or self._by_alias.get(norm)

    def require(self, key_or_alias: str) -> Marker:
        m = self.get(key_or_alias)
        if m is None:
            raise KeyError(f"Unknown biomarker: {key_or_alias!r}")
        return m

    def by_category(self, category: str) -> list[Marker]:
        return [m for m in self.markers if m.category == category]

    def by_tier(self, tier: int) -> list[Marker]:
        return [m for m in self.markers if m.tier == tier]

    def category_keys(self) -> list[str]:
        seen, out = set(), []
        for m in self.markers:
            if m.category not in seen:
                seen.add(m.category)
                out.append(m.category)
        return out

    def aliases_for(self, key: str) -> tuple[str, ...]:
        m = self.get(key)
        return m.aliases if m else ()

    # ---- classification ----------------------------------------------------

    def classify(self, key_or_alias: str, value: float | str | None) -> Status:
        """Classify a measured value against a marker's reference bands.

        For binary_flag markers, a truthy non-empty/non-"negative" value returns
        :attr:`Status.PRESENT`; otherwise :attr:`Status.ABSENT`.
        """
        marker = self.get(key_or_alias)
        if marker is None or value is None or value == "":
            return Status.UNKNOWN

        if marker.direction is Direction.BINARY_FLAG:
            return _classify_binary(value)

        try:
            v = float(value)
        except (TypeError, ValueError):
            return Status.UNKNOWN

        return _classify_numeric(v, marker.ranges, marker.direction)

    # ---- presence-aware rendering ------------------------------------------

    def present_markers(self, user_keys: Iterable[str]) -> list[Marker]:
        """Return only the markers a user has data for (resolves aliases)."""
        present: list[Marker] = []
        seen: set[str] = set()
        for k in user_keys:
            m = self.get(k)
            if m and m.canonical_key not in seen:
                seen.add(m.canonical_key)
                present.append(m)
        return present

    def present_categories(self, user_keys: Iterable[str]) -> list[str]:
        """Return the unique categories a user has at least one marker in."""
        cats: list[str] = []
        seen: set[str] = set()
        for m in self.present_markers(user_keys):
            if m.category not in seen:
                seen.add(m.category)
                cats.append(m.category)
        return cats


def _normalize_lookup(s: str) -> str:
    """Case/whitespace/punctuation-tolerant lookup key."""
    return (
        s.strip()
        .lower()
        .replace("-", " ")
        .replace("_", " ")
        .replace(",", "")
        .replace("(", "")
        .replace(")", "")
        .replace("  ", " ")
    )


def _classify_binary(value: Any) -> Status:
    if isinstance(value, (int, float)):
        return Status.PRESENT if value else Status.ABSENT
    s = str(value).strip().lower()
    if s in {"", "0", "none", "negative", "neg", "not detected", "absent", "n/a", "no"}:
        return Status.ABSENT
    return Status.PRESENT


def _classify_numeric(value: float, r: Ranges, direction: Direction) -> Status:
    """Apply tri-band classification to a numeric value."""
    # Out-of-range checks first (most severe wins).
    if r.out_of_range_low_max is not None and value < r.out_of_range_low_max:
        return Status.OUT_OF_RANGE
    if r.out_of_range_high_min is not None and value >= r.out_of_range_high_min:
        return Status.OUT_OF_RANGE

    # Optimal band.
    in_optimal = _within(value, r.optimal_min, r.optimal_max)
    if in_optimal:
        return Status.OPTIMAL

    # Borderline band.
    in_borderline = _within(value, r.borderline_min, r.borderline_max)
    if in_borderline:
        return Status.BORDERLINE

    # If we got here and direction-specific logic helps, apply it.
    if direction is Direction.LOWER_IS_BETTER:
        if r.optimal_max is not None and value <= r.optimal_max:
            return Status.OPTIMAL
    elif direction is Direction.HIGHER_IS_BETTER:
        if r.optimal_min is not None and value >= r.optimal_min:
            return Status.OPTIMAL

    # No applicable band — surface as unknown so the UI can hide it.
    return Status.UNKNOWN


def _within(value: float, lo: float | None, hi: float | None) -> bool:
    """True if value is inside ``[lo, hi]`` (either side optional)."""
    if lo is None and hi is None:
        return False
    if lo is not None and value < lo:
        return False
    if hi is not None and value > hi:
        return False
    return True


# ---------------------------------------------------------------------------
# Public loader API (cached)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> Catalog:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    markers = tuple(Marker.from_dict(m) for m in raw.get("markers", []))

    by_key: dict[str, Marker] = {}
    by_alias: dict[str, Marker] = {}
    for m in markers:
        by_key[_normalize_lookup(m.canonical_key)] = m
        by_key[_normalize_lookup(m.display_name)] = m
        for a in m.aliases:
            by_alias.setdefault(_normalize_lookup(a), m)

    return Catalog(
        schema_version=int(raw.get("schema_version", 0)),
        total_markers=int(raw.get("total_markers", len(markers))),
        categories=tuple(raw.get("categories", []) or []),
        markers=markers,
        _by_key=by_key,
        _by_alias=by_alias,
    )


def load_catalog(path: Path | str | None = None) -> Catalog:
    """Public entry point — load the catalog (cached)."""
    resolved = _resolve_catalog_path(path)
    return _load_cached(str(resolved))


def clear_cache() -> None:
    """Drop the cache — useful in tests when swapping fixture files."""
    _load_cached.cache_clear()
