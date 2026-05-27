"""OCR + structured-parse for PDF lab reports and supplement-label photos.

Strategy (in order):
  1. **PDF text layer** — `pypdf` reads selectable text. Most LabCorp/Quest
     reports are text-PDFs and skip OCR entirely. Free, fast, no API.
  2. **OpenAI vision (gpt-4o-mini)** — for images and image-only PDFs. We send
     each page/image as a base64 data-url and ask for a JSON-structured
     extraction. Requires `OPENAI_API_KEY`.
  3. **Tesseract fallback** — when no OpenAI key is configured. Uses
     `pytesseract` + (for PDFs) `pdf2image`. Returns raw text only; structured
     parse falls back to regex heuristics.

The two public entry points are:
  - `extract_bloodwork_rows(file_bytes, filename) -> list[dict]`
  - `extract_supplement_label(file_bytes, filename) -> dict`

Both degrade gracefully: if no extractor is available, they raise
`OCRUnavailable` with a clear remediation message.
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from modules.biomarker_aliases import ALIASES
from modules.llm import get_api_key


class OCRUnavailable(RuntimeError):
    """Raised when neither OpenAI nor tesseract is available."""


# ─── Helpers ────────────────────────────────────────────────────────────────

# Build alias → canonical reverse map (lowercased)
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canon, _aliases in ALIASES.items():
    _ALIAS_TO_CANONICAL[_canon.lower()] = _canon
    for _a in _aliases:
        _ALIAS_TO_CANONICAL[_a.lower().strip()] = _canon


def _canonicalize(raw_name: str) -> str | None:
    """Map a free-text biomarker name to a canonical key, or None if unknown."""
    if not raw_name:
        return None
    key = raw_name.strip().lower()
    if key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[key]
    # try without punctuation
    stripped = re.sub(r"[^a-z0-9 ]", " ", key).strip()
    stripped = re.sub(r"\s+", " ", stripped)
    return _ALIAS_TO_CANONICAL.get(stripped)


def _b64_data_url(file_bytes: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(file_bytes).decode('ascii')}"


# ─── Extractors: PDF text layer ─────────────────────────────────────────────

def _pdf_text_layer(file_bytes: bytes) -> str:
    """Try to pull selectable text out of a PDF. Returns '' on failure."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        chunks = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                chunks.append(t)
        return "\n\n".join(chunks)
    except Exception:
        return ""


# ─── Extractors: OpenAI vision ──────────────────────────────────────────────

def _openai_extract(file_bytes: bytes, mime: str, prompt: str,
                    model: str = "gpt-4o-mini") -> str:
    """Send the image/PDF page to OpenAI and return the raw response text."""
    from openai import OpenAI
    key = get_api_key()
    if not key:
        raise OCRUnavailable("No OPENAI_API_KEY configured")

    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": _b64_data_url(file_bytes, mime)}},
            ],
        }],
        max_tokens=2000,
        temperature=0.1,
    )
    return resp.choices[0].message.content or ""


# ─── Extractors: Tesseract ──────────────────────────────────────────────────

def _tesseract_image(image_bytes: bytes) -> str:
    """OCR a single image with tesseract. Returns '' if unavailable."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def _tesseract_pdf(pdf_bytes: bytes) -> str:
    """Rasterize PDF pages and OCR each. Returns '' if unavailable."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError:
        return ""
    try:
        pages = convert_from_bytes(pdf_bytes, dpi=200)
    except Exception:
        return ""
    out = []
    for p in pages:
        try:
            out.append(pytesseract.image_to_string(p))
        except Exception:
            continue
    return "\n\n".join(out)


# ─── Bloodwork PDF parser ───────────────────────────────────────────────────

_BLOODWORK_PROMPT = """You are extracting numeric biomarkers from a lab report.

Return a single JSON object with this exact shape:
{
  "draw_date": "YYYY-MM-DD or null",
  "source_lab": "LabCorp | Quest | Empire City | Other",
  "rows": [
    {"name": "biomarker name as printed", "value": 12.3, "unit": "mg/dL",
     "ref_low": 10, "ref_high": 50}
  ]
}

Rules:
- Include EVERY numeric result on the page. Skip free-text comments.
- Use the exact unit printed (mg/dL, ng/mL, mIU/L, %, etc.).
- ref_low and ref_high are the lab's printed reference range; use null if absent.
- Do not invent values; if unclear, omit the row.
- Respond with JSON only, no prose, no code fences."""


def _parse_bloodwork_text(text: str) -> list[dict[str, Any]]:
    """Fallback regex parser for raw text. Catches lines like:
        ApoB                 95   mg/dL   (40-100)
    Best-effort; OpenAI path is far more reliable.
    """
    rows: list[dict[str, Any]] = []
    if not text:
        return rows
    # rough pattern: name (letters/spaces/dashes/parens) then a number then optional unit
    pat = re.compile(
        r"^\s*([A-Za-z][A-Za-z0-9 \-()/.,]{2,40}?)\s+"
        r"(\d+\.?\d*)\s*"
        r"([A-Za-z%/μµ]+(?:/[A-Za-z]+)?)?",
        re.MULTILINE,
    )
    for m in pat.finditer(text):
        name = m.group(1).strip()
        try:
            value = float(m.group(2))
        except ValueError:
            continue
        unit = (m.group(3) or "").strip()
        canon = _canonicalize(name)
        if not canon:
            continue
        rows.append({
            "biomarker_canonical": canon,
            "name_raw": name,
            "value": value,
            "unit": unit,
            "ref_low": None,
            "ref_high": None,
        })
    return rows


def extract_bloodwork_rows(file_bytes: bytes, filename: str,
                           draw_date_hint: str | None = None) -> dict[str, Any]:
    """Extract bloodwork rows from a PDF or image.

    Returns ``{"rows": [...], "draw_date": str|None, "source_lab": str,
               "engine": str, "warnings": list[str]}``.

    ``engine`` is one of ``pdf_text+openai``, ``openai_vision``,
    ``pdf_text+regex``, ``tesseract+regex``.
    """
    name = filename.lower()
    is_pdf = name.endswith(".pdf")
    mime = "application/pdf" if is_pdf else (
        "image/png" if name.endswith(".png") else "image/jpeg"
    )
    warnings: list[str] = []

    # ── Step 1: try the cheapest path first ────────────────────────────────
    text = ""
    if is_pdf:
        text = _pdf_text_layer(file_bytes)

    # ── Step 2: if we have text + an OpenAI key, ask it to structure it ────
    api_available = bool(get_api_key())
    engine = ""
    rows: list[dict[str, Any]] = []
    draw_date: str | None = draw_date_hint
    source_lab = ""

    if text and api_available:
        # send the text alone (cheaper than vision)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=get_api_key())
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You output JSON only."},
                    {"role": "user", "content": _BLOODWORK_PROMPT + "\n\n--- LAB REPORT TEXT ---\n" + text[:12000]},
                ],
                max_tokens=2500,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(resp.choices[0].message.content or "{}")
            engine = "pdf_text+openai"
        except Exception as e:
            warnings.append(f"OpenAI text parse failed: {e}")
            parsed = {}
    elif api_available:
        # No text layer (or image input) → send to vision
        try:
            raw = _openai_extract(file_bytes, mime, _BLOODWORK_PROMPT)
            # strip code fences if present
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            engine = "openai_vision"
        except Exception as e:
            warnings.append(f"OpenAI vision parse failed: {e}")
            parsed = {}
    else:
        parsed = {}

    if parsed and isinstance(parsed, dict):
        draw_date = parsed.get("draw_date") or draw_date
        source_lab = parsed.get("source_lab") or ""
        for r in parsed.get("rows", []) or []:
            try:
                value = float(r.get("value"))
            except (TypeError, ValueError):
                continue
            name_raw = (r.get("name") or "").strip()
            canon = _canonicalize(name_raw)
            if not canon:
                warnings.append(f"Unknown biomarker: '{name_raw}' (value {value})")
                continue
            rows.append({
                "biomarker_canonical": canon,
                "name_raw": name_raw,
                "value": value,
                "unit": (r.get("unit") or "").strip(),
                "ref_low": r.get("ref_low"),
                "ref_high": r.get("ref_high"),
            })

    # ── Step 3: tesseract fallback ─────────────────────────────────────────
    if not rows:
        if is_pdf:
            t_text = text or _tesseract_pdf(file_bytes)
        else:
            t_text = _tesseract_image(file_bytes)
        if t_text:
            rows = _parse_bloodwork_text(t_text)
            engine = engine or ("pdf_text+regex" if text else "tesseract+regex")
            if not rows:
                warnings.append("OCR succeeded but no biomarkers matched the alias dictionary.")
        elif not api_available:
            raise OCRUnavailable(
                "Could not extract data: no OPENAI_API_KEY configured and "
                "tesseract is unavailable. Either set OPENAI_API_KEY in "
                "Streamlit secrets, or install tesseract + pytesseract."
            )

    return {
        "rows": rows,
        "draw_date": draw_date,
        "source_lab": source_lab,
        "engine": engine or "none",
        "warnings": warnings,
    }


# ─── Supplement label parser ────────────────────────────────────────────────

_SUPPLEMENT_PROMPT = """You are extracting structured data from a supplement / nutraceutical label photo.

Return a single JSON object with this exact shape:
{
  "product_name": "e.g. Thorne Basic B Complex",
  "brand": "e.g. Thorne",
  "category": "supplement | hormone | peptide | medication",
  "serving_size": "e.g. 1 capsule",
  "ingredients": [
    {"name": "Vitamin D3 (as cholecalciferol)", "amount": 5000, "unit": "IU",
     "pct_dv": 625}
  ],
  "directions": "as printed",
  "warnings": "as printed or empty"
}

Rules:
- Use the exact units printed (mg, mcg, IU, billion CFU, etc.).
- Set pct_dv to null if not printed.
- category defaults to "supplement" unless clearly a medication or peptide.
- Respond with JSON only, no prose, no code fences."""


def extract_supplement_label(file_bytes: bytes, filename: str) -> dict[str, Any]:
    """Extract structured supplement-label data from a photo.

    Returns ``{"parsed": {...}, "engine": str, "warnings": list[str],
               "raw_text": str}``.
    """
    name = filename.lower()
    mime = "image/png" if name.endswith(".png") else "image/jpeg"
    if name.endswith(".pdf"):
        mime = "application/pdf"

    warnings: list[str] = []
    api_available = bool(get_api_key())

    if api_available:
        try:
            raw = _openai_extract(file_bytes, mime, _SUPPLEMENT_PROMPT)
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            return {
                "parsed": parsed,
                "engine": "openai_vision",
                "warnings": warnings,
                "raw_text": "",
            }
        except Exception as e:
            warnings.append(f"OpenAI vision parse failed: {e}")

    # Tesseract fallback — raw text only, no structure
    if name.endswith(".pdf"):
        raw_text = _pdf_text_layer(file_bytes) or _tesseract_pdf(file_bytes)
    else:
        raw_text = _tesseract_image(file_bytes)

    if not raw_text:
        if not api_available:
            raise OCRUnavailable(
                "Could not extract label data: no OPENAI_API_KEY configured and "
                "tesseract is unavailable. Set OPENAI_API_KEY in Streamlit "
                "secrets for best results, or install tesseract for offline OCR."
            )
        return {"parsed": {}, "engine": "none", "warnings": warnings, "raw_text": ""}

    warnings.append("Tesseract fallback: returning raw text only. Fill in fields manually below.")
    return {
        "parsed": {},
        "engine": "tesseract",
        "warnings": warnings,
        "raw_text": raw_text,
    }
