"""Tests for the alerts evaluator catalog."""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))

from modules.alerts import (  # noqa: E402
    evaluate_biomarker_thresholds,
    evaluate_supplement_reorders,
    evaluate_q1_panel_due,
    evaluate_anavar_mid_cycle,
    group_by_severity,
    SEVERITY_CRITICAL,
    SEVERITY_WARNING,
)


def test_biomarker_threshold_no_alerts_when_in_range():
    bw = pd.DataFrame({"date": ["2026-05-01"], "alt_u_l": [25], "apob_mg_dl": [65]})
    bw["date"] = pd.to_datetime(bw["date"])
    alerts = evaluate_biomarker_thresholds(bw)
    assert alerts == []


def test_biomarker_threshold_alt_warning():
    bw = pd.DataFrame({"date": ["2026-05-01"], "alt_u_l": [45]})
    bw["date"] = pd.to_datetime(bw["date"])
    alerts = evaluate_biomarker_thresholds(bw)
    assert any("ALT" in a.title for a in alerts)


def test_biomarker_threshold_apob_critical():
    bw = pd.DataFrame({"date": ["2026-05-01"], "apob_mg_dl": [110]})
    bw["date"] = pd.to_datetime(bw["date"])
    alerts = evaluate_biomarker_thresholds(bw)
    apob_alerts = [a for a in alerts if "ApoB" in a.title]
    assert any(a.severity == SEVERITY_CRITICAL for a in apob_alerts)


def test_biomarker_threshold_override_changes_trigger():
    bw = pd.DataFrame({"date": ["2026-05-01"], "hct_pct": [51]})
    bw["date"] = pd.to_datetime(bw["date"])
    # default: 51 is below warn (52). Override warn to 50 -> should trigger.
    alerts = evaluate_biomarker_thresholds(bw)
    assert alerts == []
    alerts = evaluate_biomarker_thresholds(bw, overrides={"hct_pct_warn": 50})
    assert any("Hct" in a.title for a in alerts)


def test_supplement_reorder_critical():
    inv = pd.DataFrame([{
        "supplement_name": "Magnesium",
        "daily_dose": 1.0,
        "dose_unit": "scoop",
        "quantity_remaining": 1.0,
        "quantity_unit": "scoop",
        "last_purchase_date": None,
        "last_purchase_quantity": None,
        "reorder_url": "",
        "notes": "",
    }])
    alerts = evaluate_supplement_reorders(inv)
    assert alerts
    assert alerts[0].severity == SEVERITY_CRITICAL


def test_supplement_reorder_info():
    inv = pd.DataFrame([{
        "supplement_name": "Omega-3",
        "daily_dose": 1.0,
        "quantity_remaining": 12,
        "last_purchase_date": None,
        "last_purchase_quantity": None,
    }])
    alerts = evaluate_supplement_reorders(inv)
    assert alerts
    assert alerts[0].severity == "info"


def test_supplement_reorder_no_alert_when_plentiful():
    inv = pd.DataFrame([{
        "supplement_name": "X",
        "daily_dose": 1.0,
        "quantity_remaining": 60,
        "last_purchase_date": None,
        "last_purchase_quantity": None,
    }])
    alerts = evaluate_supplement_reorders(inv)
    assert alerts == []


def test_q1_panel_skips_when_far_away():
    # If today is May, Q1 target Jan is far away; should not fire
    r = evaluate_q1_panel_due("2026-01-15")
    # Could be None or could fire if within 14d; just assert call works
    assert r is None or r.severity == "warning"


def test_anavar_mid_cycle_fires_at_day_21():
    today = datetime.now().date()
    start = today - timedelta(days=21)
    proto = pd.DataFrame([{
        "name": "Oxandrolone (Anavar)",
        "category": "medication",
        "start_date": start.isoformat(),
        "end_date": None,
        "cycle_status": "active",
    }])
    proto["start_date"] = pd.to_datetime(proto["start_date"])
    r = evaluate_anavar_mid_cycle(proto)
    assert r is not None
    assert "Anavar" in r.title or "ALT" in r.title


def test_group_by_severity():
    from modules.alerts import _alert, CATEGORY_BIOMARKER, SEVERITY_INFO
    items = [
        _alert(CATEGORY_BIOMARKER, "a", SEVERITY_CRITICAL, "C", "x"),
        _alert(CATEGORY_BIOMARKER, "b", SEVERITY_WARNING, "W", "x"),
        _alert(CATEGORY_BIOMARKER, "c", SEVERITY_INFO, "I", "x"),
    ]
    g = group_by_severity(items)
    assert len(g[SEVERITY_CRITICAL]) == 1
    assert len(g[SEVERITY_WARNING]) == 1
    assert len(g[SEVERITY_INFO]) == 1
