"""Function Health "Lab result of record" PDF parser.

Function Health offers no public API; the only supported export is a "Lab
result of record" PDF (downloadable from my.functionhealth.com/documents).
This module parses that PDF into a DataFrame compatible with Protocōl's
bloodwork schema.

The parser is reverse-engineered from public examples (Empirical Health and
other consumer apps that ingest the same PDF) and from typical clinical-PDF
table conventions. Heuristics are intentionally defensive — tables first via
pdfplumber.extract_tables(), then a regex-on-text fallback. Both paths share
the same row-normalization logic so a partially-table-recognized PDF still
yields useful rows.

Expect to revisit name aliases and column-order heuristics once a real
Function Health PDF is available for validation (tracked in DECISIONS.md).
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

try:
    import pdfplumber  # type: ignore
except Exception:  # pragma: no cover - import-time fallback
    pdfplumber = None  # noqa: N816

from modules.biomarker_aliases import canonicalize

log = logging.getLogger(__name__)

OUTPUT_COLUMNS = [
    "biomarker",
    "biomarker_canonical",
    "value",
    "unit",
    "reference_low",
    "reference_high",
    "flag",
    "collection_date",
    "source_file",
    "source",
]

# Function Health surfaces a number of names that don't appear in the project's
# existing alias table. Extend the cross-lab map here without polluting the
# shared module; canonicalize() is tried first, then these.
FUNCTION_EXTRA_ALIASES: dict[str, str] = {
    "apo b": "apob_mg_dl",
    "apolipoprotein b": "apob_mg_dl",
    "ldl-c (direct)": "ldl_c_mg_dl",
    "hemoglobin a1c": "hba1c_pct",
    "a1c": "hba1c_pct",
    "hs-crp": "hscrp_mg_l",
    "high sensitivity crp": "hscrp_mg_l",
    "hs c-reactive protein": "hscrp_mg_l",
    "25-oh vitamin d": "vitamin_d_ng_ml",
    "25-hydroxy vitamin d": "vitamin_d_ng_ml",
    "vitamin d, 25-oh": "vitamin_d_ng_ml",
    "lipoprotein (a)": "lp_a_nmol_l",
    "lp(a)": "lp_a_nmol_l",
    "free testosterone (direct)": "testosterone_free_pg_ml",
    "testosterone, total": "testosterone_total_ng_dl",
    "tsh, 3rd generation": "tsh_uiu_ml",
    "ggt": "ggt_u_l",
    "alt (sgpt)": "alt_u_l",
    "ast (sgot)": "ast_u_l",
    "iron, total": "iron_ug_dl",
    "tibc": "tibc_ug_dl",
    "% transferrin saturation": "transferrin_saturation_pct",
    "omega-3 index": "omega_3_index_pct",
    "homa-ir": "homa_ir",
}

# Regex helpers ────────────────────────────────────────────────────────────────
# A "value" is a number (optionally with comma thousands or decimal). We allow
# optional leading sign and scientific notation just in case.
_NUM = r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?"
# Common clinical units, kept broad. The capture group is intentionally
# permissive — we'll normalize whitespace and slashes after the fact.
_UNIT = (
    r"(?:%|mg/dL|mg/dl|mg/L|mg/l|g/dL|g/dl|g/L|mEq/L|mmol/L|mIU/mL|uIU/mL|"
    r"µIU/mL|µg/dL|ug/dL|ug/dl|ng/mL|ng/dL|pg/mL|nmol/L|µmol/L|umol/L|"
    r"fL|pg|IU/mL|IU/L|U/L|K/uL|M/uL|10\^3/uL|10\^6/uL|ratio|mm/hr|"
    r"index|score|/uL|cells/uL)"
)
_RANGE = (
    rf"(?P<low>{_NUM})\s*[-–to]+\s*(?P<high>{_NUM})"
    rf"|<\s*(?P<lt>{_NUM})"
    rf"|>\s*(?P<gt>{_NUM})"
)

LINE_RE = re.compile(
    rf"^(?P<name>[A-Za-z][A-Za-z0-9 ,\-\(\)/\.%]+?)\s+"
    rf"(?P<value>{_NUM})\s*"
    rf"(?P<unit>{_UNIT})?\s*"
    rf"(?:(?:{_RANGE}))?\s*$",
    re.IGNORECASE,
)

DATE_PATTERNS = [
    re.compile(r"(?:Collected|Collection Date|Drawn|Specimen Collected)[:\s]+([0-9/\-A-Za-z, ]{6,20})", re.IGNORECASE),
    re.compile(r"\bDate(?:\s+of\s+Service)?[:\s]+([0-9/\-A-Za-z, ]{6,20})", re.IGNORECASE),
]


@dataclass
class ParsedRow:
    name: str
    value: float
    unit: str | None
    low: float | None
    high: float | None


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_function_pdf(file_bytes_or_path: bytes | str | Path | io.BytesIO) -> pd.DataFrame:
    """Parse a Function Health Lab Result of Record PDF.

    Returns an empty DataFrame on any failure (malformed PDF, missing
    pdfplumber, no recognizable rows) — never raises.
    """
    if pdfplumber is None:
        log.warning("pdfplumber not available; returning empty DataFrame")
        return _empty_df()

    source_file = _source_file_name(file_bytes_or_path)
    pdf_arg = _coerce_to_pdfplumber_arg(file_bytes_or_path)

    rows: list[ParsedRow] = []
    collection_date: str | None = None
    metadata_creation: str | None = None

    try:
        with pdfplumber.open(pdf_arg) as pdf:
            try:
                metadata_creation = _extract_metadata_date(pdf.metadata or {})
            except Exception:
                metadata_creation = None

            for page_idx, page in enumerate(pdf.pages):
                if collection_date is None and page_idx < 2:
                    try:
                        collection_date = _find_date_in_text(page.extract_text() or "")
                    except Exception:
                        pass

                # Table-first
                table_rows: list[ParsedRow] = []
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for tbl in tables:
                    table_rows.extend(_rows_from_table(tbl))

                if table_rows:
                    rows.extend(table_rows)
                    continue

                # Regex fallback
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                rows.extend(_rows_from_text(text))
    except Exception as exc:
        log.warning("parse_function_pdf failed: %s", exc)
        return _empty_df()

    if collection_date is None:
        collection_date = metadata_creation

    return _build_dataframe(rows, collection_date, source_file)


# ── Internals ──────────────────────────────────────────────────────────────────

def _empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=OUTPUT_COLUMNS)


def _source_file_name(arg: Any) -> str:
    if isinstance(arg, (str, Path)):
        return Path(str(arg)).name
    return "function_health.pdf"


def _coerce_to_pdfplumber_arg(arg: Any) -> Any:
    if isinstance(arg, (str, Path)):
        return arg
    if isinstance(arg, bytes):
        return io.BytesIO(arg)
    return arg  # already a file-like


def _extract_metadata_date(meta: dict) -> str | None:
    raw = meta.get("CreationDate") or meta.get("ModDate")
    if not raw:
        return None
    s = str(raw)
    # Common PDF format: "D:20260115093045-07'00'"
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _find_date_in_text(text: str) -> str | None:
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        candidate = m.group(1).strip().rstrip(",")
        iso = _normalize_date(candidate)
        if iso:
            return iso
    return None


def _normalize_date(raw: str) -> str | None:
    raw = raw.strip().rstrip(",")
    formats = [
        "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y",
        "%B %d, %Y", "%b %d, %Y", "%d %b %Y", "%d %B %Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _to_float(s: str | None) -> float | None:
    if s is None:
        return None
    s = str(s).replace(",", "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _rows_from_text(text: str) -> list[ParsedRow]:
    out: list[ParsedRow] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            continue
        name = m.group("name").strip()
        # Skip header-ish lines
        if name.lower() in {"biomarker", "test", "result", "marker"}:
            continue
        value = _to_float(m.group("value"))
        if value is None:
            continue
        unit = (m.group("unit") or "").strip() or None
        low = _to_float(m.group("low") or m.group("gt"))
        high = _to_float(m.group("high") or m.group("lt"))
        # `< X`  → high = X, low = 0;  `> X` → low = X, high = None
        if m.group("lt"):
            low, high = 0.0, _to_float(m.group("lt"))
        elif m.group("gt"):
            low, high = _to_float(m.group("gt")), None
        out.append(ParsedRow(name=name, value=value, unit=unit, low=low, high=high))
    return out


def _rows_from_table(table: list[list[str | None]]) -> list[ParsedRow]:
    """Heuristically read rows from a pdfplumber table.

    Function-style tables typically have columns like:
      Biomarker | Result | Unit | Reference Range | Flag | ...
    Column order varies, so we detect header semantics on the first row.
    """
    if not table or len(table) < 2:
        return []

    header = [(c or "").strip().lower() for c in table[0]]
    idx_name = _first_col(header, ("biomarker", "test", "marker", "analyte", "name"))
    idx_value = _first_col(header, ("result", "value", "your value", "your result"))
    idx_unit = _first_col(header, ("unit", "units"))
    idx_range = _first_col(header, ("reference range", "range", "ref range", "reference"))

    # If no obvious header, treat first 4 cols as (name, value, unit, range)
    if idx_name is None or idx_value is None:
        idx_name, idx_value, idx_unit, idx_range = 0, 1, 2, 3
        data_rows: Iterable[list[str | None]] = table
    else:
        data_rows = table[1:]

    out: list[ParsedRow] = []
    for raw in data_rows:
        cells = [(c or "").strip() for c in raw]
        if len(cells) <= max(filter(lambda x: x is not None, [idx_name, idx_value])):
            continue
        name = cells[idx_name] if idx_name is not None and idx_name < len(cells) else ""
        if not name or name.lower() in {"biomarker", "test", "marker"}:
            continue
        value = _to_float(cells[idx_value]) if idx_value is not None and idx_value < len(cells) else None
        if value is None:
            continue
        unit = cells[idx_unit] if (idx_unit is not None and idx_unit < len(cells)) else None
        unit = unit or None
        low, high = (None, None)
        if idx_range is not None and idx_range < len(cells):
            low, high = _parse_range_cell(cells[idx_range])
        out.append(ParsedRow(name=name, value=value, unit=unit, low=low, high=high))
    return out


def _first_col(header: list[str], needles: tuple[str, ...]) -> int | None:
    for i, cell in enumerate(header):
        for n in needles:
            if n in cell:
                return i
    return None


def _parse_range_cell(s: str) -> tuple[float | None, float | None]:
    if not s:
        return (None, None)
    s = s.replace("–", "-").strip()
    m = re.match(rf"\s*({_NUM})\s*-\s*({_NUM})\s*$", s)
    if m:
        return (_to_float(m.group(1)), _to_float(m.group(2)))
    m = re.match(rf"\s*<\s*({_NUM})\s*$", s)
    if m:
        return (0.0, _to_float(m.group(1)))
    m = re.match(rf"\s*>\s*({_NUM})\s*$", s)
    if m:
        return (_to_float(m.group(1)), None)
    return (None, None)


def _canonical_for(name: str) -> str | None:
    """Try project's canonicalize() first, then Function-specific extras."""
    can = canonicalize(name)
    if can:
        return can
    cleaned = re.sub(r"\s+", " ", name.lower().strip())
    return FUNCTION_EXTRA_ALIASES.get(cleaned)


def _flag_for(value: float, low: float | None, high: float | None) -> str:
    if high is not None and value > high:
        return "High"
    if low is not None and value < low:
        return "Low"
    return "Optimal"


def _build_dataframe(rows: list[ParsedRow], collection_date: str | None,
                     source_file: str) -> pd.DataFrame:
    out: list[dict] = []
    for r in rows:
        canon = _canonical_for(r.name)
        if canon is None:
            log.info("function_health_pdf: unrecognized biomarker name '%s'", r.name)
        out.append({
            "biomarker": r.name,
            "biomarker_canonical": canon,
            "value": r.value,
            "unit": r.unit,
            "reference_low": r.low,
            "reference_high": r.high,
            "flag": _flag_for(r.value, r.low, r.high),
            "collection_date": collection_date,
            "source_file": source_file,
            "source": "function_health",
        })
    if not out:
        return _empty_df()
    return pd.DataFrame(out, columns=OUTPUT_COLUMNS)
