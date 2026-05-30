"""v3.5 — changelog parsing, unseen badge, banner dismissal."""
from __future__ import annotations

import pytest

from _v35_v36_fixtures import isolate, make_store  # noqa: F401

from modules import changelog


SAMPLE = """# Changelog

## v3.6 — 2026-06-01

### Added
- NPS micro-survey
- Drop-off detector

### Changed
- Feedback widget is now structured

## v3.5 — 2026-05-31

### Added
- Account deletion
"""


@pytest.fixture
def changelog_file(tmp_path):
    p = tmp_path / "CHANGELOG.md"
    p.write_text(SAMPLE)
    return p


def test_parse_newest_first(changelog_file):
    versions = changelog.parse_changelog(changelog_file)
    assert [v.version for v in versions] == ["v3.6", "v3.5"]
    assert versions[0].date == "2026-06-01"
    assert "Added" in versions[0].sections
    assert any("NPS" in b for b in versions[0].sections["Added"])


def test_latest_version(changelog_file):
    assert changelog.latest_version(changelog_file) == "v3.6"


def test_has_unseen_then_seen(isolate, changelog_file):
    store = make_store("alice")
    assert changelog.has_unseen(store, changelog_file) is True
    changelog.mark_seen(store, changelog_file)
    assert changelog.has_unseen(store, changelog_file) is False


def test_banner_dismissal(isolate, changelog_file):
    store = make_store("alice")
    assert changelog.should_show_home_banner(store, changelog_file) is True
    changelog.dismiss_banner("v3.6", store)
    assert changelog.banner_dismissed("v3.6", store) is True
    assert changelog.should_show_home_banner(store, changelog_file) is False
