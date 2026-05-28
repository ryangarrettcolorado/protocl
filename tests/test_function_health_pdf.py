"""Tests for the Function Health PDF parser.

We use fpdf2 (already a project dep, used by the clinician summary) to render
tiny synthetic PDFs for the integration-level cases. The unit-level cases
exercise the parser's pure helpers directly so they don't depend on the PDF
layer at all.
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

# Make `from modules....` imports work the same way the Streamlit app does.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "protocl"))

from modules.function_health_pdf import (  # noqa: E402
    _canonical_for,
    _flag_for,
    _rows_from_text,
    parse_function_pdf,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pdf(lines: list[str]) -> bytes:
    """Render a 1-page PDF containing the given lines, return raw bytes."""
    from fpdf import FPDF  # local import — keeps the unit tests fast
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.cell(0, 6, txt=line, ln=1)
    out = pdf.output(dest="S")
    # fpdf2 returns bytearray; older fpdf returns str-latin1
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


# ── Cases ─────────────────────────────────────────────────────────────────────

def test_empty_bytes_returns_empty_dataframe():
    df = parse_function_pdf(b"")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_garbage_bytes_returns_empty_dataframe():
    df = parse_function_pdf(b"this is not a pdf at all")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_nonexistent_path_returns_empty_dataframe():
    df = parse_function_pdf("/tmp/__does_not_exist__.pdf")
    assert df.empty


def test_canonical_apob_aliases_map_to_apob():
    assert _canonical_for("ApoB") == "apob_mg_dl"
    assert _canonical_for("Apolipoprotein B") == "apob_mg_dl"
    assert _canonical_for("APO B") == "apob_mg_dl"


def test_canonical_unknown_returns_none():
    assert _canonical_for("Wibble Factor Z") is None


def test_flag_logic():
    assert _flag_for(78, 0, 90) == "Optimal"
    assert _flag_for(165, 0, 100) == "High"
    assert _flag_for(1.3, 2.6, 24.9) == "Low"
    assert _flag_for(50, None, None) == "Optimal"


def test_text_fallback_single_optimal_row():
    rows = _rows_from_text("ApoB 78 mg/dL 0 - 90")
    assert len(rows) == 1
    r = rows[0]
    assert r.name == "ApoB"
    assert r.value == 78.0
    assert r.unit == "mg/dL"
    assert r.low == 0.0 and r.high == 90.0


def test_text_fallback_high_flag():
    rows = _rows_from_text("LDL 165 mg/dL 0 - 100")
    assert len(rows) == 1
    assert rows[0].value == 165.0
    assert rows[0].high == 100.0


def test_text_fallback_less_than_range():
    rows = _rows_from_text("hs-CRP 0.4 mg/L < 1.0")
    assert len(rows) == 1
    r = rows[0]
    assert r.value == 0.4
    # `< X` is treated as upper-bound only (low pinned to 0)
    assert r.high == 1.0
    assert r.low == 0.0


def test_synthetic_pdf_end_to_end():
    """Full integration: render a tiny PDF, parse it, assert shape & flag."""
    pdf_bytes = _make_pdf([
        "Function Health - Lab Result of Record",
        "Collected: 2026-01-15",
        "ApoB 78 mg/dL 0 - 90",
        "LDL 165 mg/dL 0 - 100",
        "HDL 55 mg/dL 40 - 100",
    ])
    df = parse_function_pdf(pdf_bytes)
    assert not df.empty, "parser produced no rows from synthetic PDF"
    # Must have all 9 schema columns
    for col in (
        "biomarker", "biomarker_canonical", "value", "unit",
        "reference_low", "reference_high", "flag",
        "collection_date", "source_file", "source",
    ):
        assert col in df.columns
    # Source label is always set
    assert (df["source"] == "function_health").all()
    # Apolipoprotein B canonical lookup works through the full pipeline
    apob = df[df["biomarker"].str.lower().str.startswith("apob")]
    assert not apob.empty
    assert apob.iloc[0]["biomarker_canonical"] == "apob_mg_dl"
    assert apob.iloc[0]["flag"] == "Optimal"
    # The High flag fires correctly
    ldl = df[df["biomarker"].str.lower().str.startswith("ldl")]
    assert not ldl.empty
    assert ldl.iloc[0]["flag"] == "High"
    # Collection date threaded through
    assert (df["collection_date"] == "2026-01-15").all()
