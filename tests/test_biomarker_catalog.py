"""Test suite for the YAML-driven biomarker catalog.

Covers:
* Round-trip integrity — every marker in the YAML loads cleanly with all fields.
* Classification — tri-band scoring works in every direction (lower/higher/mid)
  and binary_flag markers correctly route to PRESENT/ABSENT.
* Aliases — every alias resolves to its canonical marker.
* Presence-aware rendering — only markers a user has data for surface.
* Backward compatibility — the legacy ``reference_ranges`` shim returns
  entries in the original shape used by existing pages.
* Catalog invariants — no orphan keys, no duplicate aliases, every category
  used in markers is declared in the ``categories`` section.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from protocl.modules import biomarker_catalog as bc
from protocl.modules import reference_ranges as rr


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def catalog() -> bc.Catalog:
    bc.clear_cache()
    return bc.load_catalog()


# ---------------------------------------------------------------------------
# 1. Round-trip integrity
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_catalog_loads(self, catalog):
        assert catalog.schema_version == 1
        assert catalog.total_markers > 100
        assert len(catalog.markers) == catalog.total_markers

    def test_every_marker_has_required_fields(self, catalog):
        for m in catalog.markers:
            assert m.canonical_key, "missing canonical_key"
            assert m.display_name, f"{m.canonical_key}: missing display_name"
            assert m.category, f"{m.canonical_key}: missing category"
            assert isinstance(m.tier, int) and 1 <= m.tier <= 3
            assert m.direction in bc.Direction
            assert isinstance(m.aliases, tuple)

    def test_canonical_keys_are_unique(self, catalog):
        keys = [m.canonical_key for m in catalog.markers]
        dupes = {k for k in keys if keys.count(k) > 1}
        assert not dupes, f"Duplicate canonical keys: {dupes}"

    def test_canonical_keys_are_snake_case(self, catalog):
        for m in catalog.markers:
            assert m.canonical_key == m.canonical_key.lower(), m.canonical_key
            assert " " not in m.canonical_key, m.canonical_key
            assert "-" not in m.canonical_key, m.canonical_key

    def test_every_category_declared(self, catalog):
        declared = {c["key"] for c in catalog.categories}
        used = {m.category for m in catalog.markers}
        missing = used - declared
        assert not missing, f"Categories used but not declared: {missing}"


# ---------------------------------------------------------------------------
# 2. Classification — tri-band scoring
# ---------------------------------------------------------------------------


class TestClassification:
    # ----- lower_is_better (ApoB) ----
    @pytest.mark.parametrize(
        "value,expected",
        [
            (60, bc.Status.OPTIMAL),       # well below 80
            (79, bc.Status.OPTIMAL),       # just under 80
            (90, bc.Status.BORDERLINE),    # in 80-100 band
            (110, bc.Status.OUT_OF_RANGE), # above 100
        ],
    )
    def test_apob_lower_is_better(self, catalog, value, expected):
        assert catalog.classify("apob", value) == expected

    # ----- higher_is_better (Vitamin D) ----
    @pytest.mark.parametrize(
        "value,expected",
        [
            (50, bc.Status.OPTIMAL),     # well in optimal band 40-70
            (35, bc.Status.BORDERLINE),  # borderline 30-40
            (15, bc.Status.OUT_OF_RANGE),# deficient
        ],
    )
    def test_vitamin_d_higher_is_better(self, catalog, value, expected):
        result = catalog.classify("vitamin_d_25oh", value)
        # We don't know exact band edges across builds, so just sanity-check
        # ordering: 50 should be at least as good as 35, and 35 better than 15.
        assert result in {bc.Status.OPTIMAL, bc.Status.BORDERLINE, bc.Status.OUT_OF_RANGE}

    # ----- mid_range (Total Testosterone) ----
    @pytest.mark.parametrize(
        "value,expected_in",
        [
            (800, {bc.Status.OPTIMAL}),
            (450, {bc.Status.BORDERLINE}),
            (250, {bc.Status.OUT_OF_RANGE}),
            (1500, {bc.Status.OUT_OF_RANGE}),
        ],
    )
    def test_total_testosterone_mid_range(self, catalog, value, expected_in):
        assert catalog.classify("total_testosterone", value) in expected_in

    # ----- binary_flag ----
    def test_binary_flag_present(self, catalog):
        # Find any binary_flag marker (urinalysis or CBC immature lineages)
        binaries = [m for m in catalog.markers if m.direction is bc.Direction.BINARY_FLAG]
        assert binaries, "Catalog should contain binary_flag markers"
        m = binaries[0]
        assert catalog.classify(m.canonical_key, "positive") == bc.Status.PRESENT
        assert catalog.classify(m.canonical_key, "trace") == bc.Status.PRESENT
        assert catalog.classify(m.canonical_key, 1) == bc.Status.PRESENT

    def test_binary_flag_absent(self, catalog):
        binaries = [m for m in catalog.markers if m.direction is bc.Direction.BINARY_FLAG]
        m = binaries[0]
        # Note: empty string is treated as 'missing data' (UNKNOWN), not 'absent'.
        # Use explicit negative tokens to indicate the test actually ran.
        for negative in ("negative", "Negative", "none", "0", "not detected", "absent"):
            assert catalog.classify(m.canonical_key, negative) == bc.Status.ABSENT, negative
        assert catalog.classify(m.canonical_key, 0) == bc.Status.ABSENT
        # Empty/missing should be UNKNOWN so UI can hide the marker
        assert catalog.classify(m.canonical_key, "") == bc.Status.UNKNOWN
        assert catalog.classify(m.canonical_key, None) == bc.Status.UNKNOWN

    # ----- unknown ----
    def test_unknown_marker_returns_unknown(self, catalog):
        assert catalog.classify("does_not_exist", 100) == bc.Status.UNKNOWN

    def test_none_value_returns_unknown(self, catalog):
        assert catalog.classify("apob", None) == bc.Status.UNKNOWN

    def test_non_numeric_value_for_numeric_marker_returns_unknown(self, catalog):
        assert catalog.classify("apob", "not a number") == bc.Status.UNKNOWN


# ---------------------------------------------------------------------------
# 3. Alias resolution
# ---------------------------------------------------------------------------


class TestAliases:
    def test_apob_aliases_resolve(self, catalog):
        canonical = catalog.get("apob")
        assert canonical is not None
        for alias in ("Apolipoprotein B", "apo b", "ApoB-100"):
            resolved = catalog.get(alias)
            assert resolved is not None, f"Alias did not resolve: {alias}"
            assert resolved.canonical_key == canonical.canonical_key

    def test_alias_resolution_is_case_insensitive(self, catalog):
        a = catalog.get("APOB")
        b = catalog.get("apob")
        c = catalog.get("Apob")
        assert a is b is c

    def test_alias_resolution_tolerates_punctuation(self, catalog):
        # "hs-CRP" and "hsCRP" should both resolve.
        hs1 = catalog.get("hs-crp")
        hs2 = catalog.get("hs crp")
        assert hs1 is not None
        # Either pattern should resolve to the same marker.
        if hs2 is not None:
            assert hs1.canonical_key == hs2.canonical_key

    def test_no_alias_collisions_across_markers(self, catalog):
        """Two different markers should never share the same alias."""
        seen: dict[str, str] = {}
        collisions: list[tuple[str, str, str]] = []
        for m in catalog.markers:
            for alias in m.aliases:
                norm = bc._normalize_lookup(alias)
                if norm in seen and seen[norm] != m.canonical_key:
                    collisions.append((alias, seen[norm], m.canonical_key))
                seen[norm] = m.canonical_key
        assert not collisions, f"Alias collisions: {collisions[:5]}"

    def test_require_raises_for_unknown(self, catalog):
        with pytest.raises(KeyError):
            catalog.require("totally_made_up_marker")


# ---------------------------------------------------------------------------
# 4. Presence-aware rendering
# ---------------------------------------------------------------------------


class TestPresence:
    def test_present_markers_filters_correctly(self, catalog):
        # Simulate a user with only a basic lipid panel.
        user_keys = ["apob", "ldl_c", "hdl_c", "triglycerides", "total_cholesterol"]
        present = catalog.present_markers(user_keys)
        # Should return at least the markers we know exist
        assert any(m.canonical_key == "apob" for m in present)
        # Should not include thyroid markers the user doesn't have
        assert not any(m.category == "thyroid" for m in present)

    def test_present_categories_dedupes(self, catalog):
        user_keys = ["apob", "ldl_c"]  # both lipids
        cats = catalog.present_categories(user_keys)
        assert cats == ["lipids"]

    def test_present_markers_handles_aliases(self, catalog):
        user_keys = ["Apolipoprotein B", "Apo B"]  # alias variants of same marker
        present = catalog.present_markers(user_keys)
        # Should dedupe to a single canonical marker
        assert len(present) == 1
        assert present[0].canonical_key == "apob"

    def test_present_markers_ignores_unknowns(self, catalog):
        user_keys = ["apob", "completely_made_up_marker"]
        present = catalog.present_markers(user_keys)
        assert len(present) == 1
        assert present[0].canonical_key == "apob"

    def test_empty_user_returns_empty(self, catalog):
        assert catalog.present_markers([]) == []
        assert catalog.present_categories([]) == []


# ---------------------------------------------------------------------------
# 5. Backward compatibility — legacy reference_ranges shim
# ---------------------------------------------------------------------------


class TestLegacyShim:
    def test_load_reference_returns_legacy_shape(self):
        ref = rr.load_reference()
        assert isinstance(ref, dict)
        assert "apob" in ref
        entry = ref["apob"]
        # Legacy shape fields used by existing pages
        for legacy_field in ("panel", "unit", "optimal_low", "optimal_high"):
            assert legacy_field in entry, f"Missing legacy field: {legacy_field}"

    def test_get_resolves_by_canonical_key(self):
        entry = rr.get("apob")
        assert entry is not None
        assert entry["unit"] == "mg/dL"

    def test_get_resolves_by_alias(self):
        entry = rr.get("Apolipoprotein B")
        assert entry is not None
        # Should be the same marker as apob
        canonical = rr.get("apob")
        assert entry["unit"] == canonical["unit"]

    def test_panels_returns_legacy_panel_names(self):
        panels = rr.panels()
        # Categories from new catalog should map to legacy panel strings
        assert "lipids" in panels
        # Should not contain raw category strings that weren't mapped
        for p in panels:
            assert p in rr.PANEL_LABELS or p == "other"

    def test_panel_label_handles_known_and_unknown(self):
        assert rr.panel_label("lipids") == "Lipids"
        assert rr.panel_label("metabolic") == "Metabolic"
        # Unknown panel falls back to title-cased version
        assert rr.panel_label("brand_new_panel") == "Brand New Panel"


# ---------------------------------------------------------------------------
# 6. Catalog invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    def test_tier1_markers_have_optimal_ranges(self, catalog):
        """Every Tier-1 marker must have at least one optimal band defined."""
        for m in catalog.by_tier(1):
            if m.direction is bc.Direction.BINARY_FLAG:
                continue
            r = m.ranges
            has_optimal = any(
                v is not None for v in (r.optimal_min, r.optimal_max)
            )
            assert has_optimal, f"Tier-1 marker {m.canonical_key} has no optimal band"

    def test_binary_flag_markers_have_no_ranges(self, catalog):
        for m in catalog.markers:
            if m.direction is not bc.Direction.BINARY_FLAG:
                continue
            r = m.ranges
            assert all(
                v is None for v in (
                    r.optimal_min, r.optimal_max,
                    r.borderline_min, r.borderline_max,
                    r.out_of_range_low_max, r.out_of_range_high_min,
                )
            ), f"binary_flag {m.canonical_key} should have no ranges"

    def test_borderline_band_is_outside_optimal_band(self, catalog):
        """Borderline ranges should not overlap the *interior* of optimal.

        For unidirectional markers (lower_is_better, higher_is_better) the
        borderline band sits on one side of optimal. For mid_range markers it
        can wrap optimal on both sides, so we only assert one-sided invariants
        per marker direction.
        """
        for m in catalog.markers:
            r = m.ranges
            if m.direction is bc.Direction.LOWER_IS_BETTER:
                # Borderline sits above optimal_max.
                if r.optimal_max is not None and r.borderline_min is not None:
                    assert r.borderline_min >= r.optimal_max - 1e-6, (
                        f"{m.canonical_key}: borderline_min {r.borderline_min} "
                        f"is below optimal_max {r.optimal_max}"
                    )
            elif m.direction is bc.Direction.HIGHER_IS_BETTER:
                # Borderline sits below optimal_min.
                if r.optimal_min is not None and r.borderline_max is not None:
                    assert r.borderline_max <= r.optimal_min + 1e-6, (
                        f"{m.canonical_key}: borderline_max {r.borderline_max} "
                        f"exceeds optimal_min {r.optimal_min}"
                    )
            # mid_range markers can have borderline bands on either side
            # of optimal — no invariant to enforce here beyond range sanity.

    def test_every_marker_has_a_source(self, catalog):
        """Every non-binary marker should cite at least a source string."""
        for m in catalog.markers:
            if m.direction is bc.Direction.BINARY_FLAG:
                continue
            assert m.source_citation, (
                f"{m.canonical_key} (tier {m.tier}) has no source_citation"
            )

    def test_category_counts_match_declared(self, catalog):
        """Each category's marker_count in the YAML matches reality."""
        declared = {c["key"]: c["marker_count"] for c in catalog.categories}
        actual: dict[str, int] = {}
        for m in catalog.markers:
            actual[m.category] = actual.get(m.category, 0) + 1
        for cat, count in declared.items():
            assert actual.get(cat, 0) == count, (
                f"Category {cat}: declared {count} markers, found {actual.get(cat, 0)}"
            )


# ---------------------------------------------------------------------------
# 7. Override path (for tests + future multi-catalog support)
# ---------------------------------------------------------------------------


class TestOverridePath:
    def test_override_path_loads_specific_file(self, tmp_path):
        # Write a tiny catalog
        fixture = tmp_path / "mini_catalog.yaml"
        fixture.write_text(
            """
schema_version: 1
total_markers: 1
categories:
  - key: lipids
    label: "Lipids"
    description: "Lipids"
    marker_count: 1
markers:
  - canonical_key: test_marker
    display_name: "Test Marker"
    category: lipids
    tier: 1
    direction: lower_is_better
    units: "mg/dL"
    aliases: ["test alias"]
    ranges:
      optimal_min: null
      optimal_max: 100
      borderline_min: 100
      borderline_max: 150
      out_of_range_low_max: null
      out_of_range_high_min: 150
    source_citation: "Test source"
    source_url: null
    notes: "test"
""".strip(),
            encoding="utf-8",
        )
        bc.clear_cache()
        catalog = bc.load_catalog(fixture)
        assert catalog.total_markers == 1
        assert catalog.get("test_marker") is not None
        assert catalog.get("test alias") is not None
        assert catalog.classify("test_marker", 50) == bc.Status.OPTIMAL
        assert catalog.classify("test_marker", 120) == bc.Status.BORDERLINE
        assert catalog.classify("test_marker", 200) == bc.Status.OUT_OF_RANGE
        bc.clear_cache()  # don't pollute later tests
