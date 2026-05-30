"""v3.3 — data minimization: prompts must never carry PII (spec 2.3)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

from explainers import llm


def test_scrub_strips_pii_keys():
    payload = {
        "email": "ryan@gmail.com",
        "name": "Ryan Garrett",
        "profile_id": "ryan",
        "value": 95,
        "points": [{"date": "2026-01-01", "value": 1}],
    }
    clean = llm.scrub_pii(payload)
    assert "email" not in clean
    assert "name" not in clean
    assert "profile_id" not in clean
    assert clean["value"] == 95
    assert clean["points"] == [{"date": "2026-01-01", "value": 1}]


def test_scrub_redacts_embedded_email_strings():
    clean = llm.scrub_pii({"note": "contact me at ryan@gmail.com please"})
    assert "ryan@gmail.com" not in clean["note"]
    assert "[redacted]" in clean["note"]


def test_scrub_is_recursive_through_lists_and_dicts():
    clean = llm.scrub_pii({"rows": [{"name": "X", "v": 1}, {"name": "Y", "v": 2}]})
    assert all("name" not in r for r in clean["rows"])


def test_build_prompt_contains_no_email():
    prompt = llm.build_prompt("Explain ApoB.", {
        "email": "leak@gmail.com", "biomarker": "apob_mg_dl", "value": 95,
    })
    assert "leak@gmail.com" not in prompt
    assert "apob_mg_dl" in prompt


def test_assert_no_pii_blocks_email():
    with pytest.raises(ValueError):
        llm.assert_no_pii("here is data for leak@gmail.com")


def test_assert_no_pii_blocks_known_name_and_email():
    with pytest.raises(ValueError):
        llm.assert_no_pii("data for Ryan Garrett", names=["Ryan Garrett"])
    with pytest.raises(ValueError):
        llm.assert_no_pii("sent to ryan@x.com", emails=["ryan@x.com"])


def test_assert_no_pii_passes_clean_prompt():
    # Should not raise.
    llm.assert_no_pii("ApoB rose from 40 to 70 over two quarters.",
                      names=["Ryan Garrett"], emails=["ryan@x.com"])


def test_model_tier_routing_is_cost_controlled():
    assert llm.MODEL_TIER12 == "gpt-4o-mini"
    assert llm.MODEL_TIER3 == "gpt-4o"
    assert llm.MODEL_TIER12 != llm.MODEL_TIER3


def test_disclaimer_appended_once():
    once = llm.with_disclaimer("Body text.")
    twice = llm.with_disclaimer(once)
    assert once.count(llm.DISCLAIMER) == 1
    assert twice.count(llm.DISCLAIMER) == 1
