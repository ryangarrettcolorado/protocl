"""Function Health PDF import — upload a "Lab result of record" PDF, review the
parsed biomarkers, and append them to bloodwork.csv.

Function Health offers no public API; this page accepts the PDF the user
downloads from my.functionhealth.com/documents and runs it through
modules.function_health_pdf.parse_function_pdf.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.charts import full_height
from modules.data_loader import (
    DATA_DIR, DEFAULT_USER, load_data, refresh_data,
)
from modules.function_health_pdf import parse_function_pdf
from modules.llm import llm_badge
from modules.theme import inject_css, render_section_header


inject_css()

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_badge = st.columns([6, 1])
with col_title:
    st.title("Function Health Import")
    st.caption(
        "Upload your Function Health *Lab result of record* PDF and we'll parse, "
        "preview, and merge biomarkers into your bloodwork history."
    )
with col_badge:
    st.markdown(llm_badge(), unsafe_allow_html=True)


# ── Sources expander (provenance) ────────────────────────────────────────────
with st.expander("📚 Sources Informing Design", expanded=False):
    st.markdown("""
- **Function Health** publicly states there is **no public API** for member data
  (see their Help Center / FAQ). The only supported export is the *Lab result
  of record* PDF available at `my.functionhealth.com/documents`.
- **Empirical Health** and several other consumer-health apps already ingest
  the same Function PDF via published flows — confirming the layout is
  reliably parseable.
- **HIPAA-aligned local processing.** The PDF is parsed in-process; no file
  contents leave the Streamlit app. Only the structured biomarker rows are
  written to disk, into the same `bloodwork.csv` used by Quest / LabCorp.
""")


# ── Uploader ──────────────────────────────────────────────────────────────────
upload = st.file_uploader(
    "Function Health Lab Result of Record (PDF)",
    type=["pdf"],
    accept_multiple_files=False,
    help="Download from https://my.functionhealth.com/documents",
)

if upload is None:
    st.info(
        "Drop a PDF above to begin. Nothing is uploaded externally — parsing "
        "runs locally inside this Streamlit process."
    )
    st.stop()


# ── Parse ─────────────────────────────────────────────────────────────────────
file_bytes = upload.read()
with st.spinner("Parsing PDF…"):
    parsed = parse_function_pdf(file_bytes)
# Always attach the real filename (the parser only sees bytes).
if not parsed.empty:
    parsed["source_file"] = upload.name

if parsed.empty:
    st.error(
        "No biomarker rows were recognized. The PDF may be image-only, "
        "encrypted, or use a layout the parser hasn't been tuned for yet. "
        "Try a different file or share the PDF for parser tuning."
    )
    st.stop()


# ── Top-line counts ───────────────────────────────────────────────────────────
n_total = len(parsed)
n_recognized = int(parsed["biomarker_canonical"].notna().sum())
n_unrecognized = n_total - n_recognized
detected_date = parsed["collection_date"].dropna().iloc[0] if (
    parsed["collection_date"].notna().any()
) else "—"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Biomarkers parsed", n_total)
c2.metric("Recognized", n_recognized)
c3.metric("Unrecognized", n_unrecognized)
c4.metric("Collection date", detected_date)

if n_unrecognized:
    st.warning(
        f"{n_unrecognized} biomarker name(s) didn't match the canonical alias "
        "table — these can still be imported but will appear under their raw "
        "name in `bloodwork.csv`. Add aliases to "
        "`modules/biomarker_aliases.py` to fold them into your historical "
        "trends."
    )


# ── Preview ───────────────────────────────────────────────────────────────────
render_section_header("Parsed biomarkers", "Review before import")

preview = parsed.copy()
preview = preview[[
    "biomarker", "biomarker_canonical", "value", "unit",
    "reference_low", "reference_high", "flag", "collection_date",
]]
st.dataframe(
    preview,
    use_container_width=True,
    height=full_height(len(preview)),
    hide_index=True,
)


# ── Import button ─────────────────────────────────────────────────────────────
st.divider()

if not st.button("📥 Import to Bloodwork", type="primary"):
    st.stop()


# ── Append + dedupe ───────────────────────────────────────────────────────────
user_dir = DATA_DIR / DEFAULT_USER
if not user_dir.exists():
    user_dir = DATA_DIR
bw_path = user_dir / "bloodwork.csv"
log_path = user_dir / "import_log.csv"

# Load existing
if bw_path.exists():
    existing = pd.read_csv(bw_path)
else:
    existing = pd.DataFrame(columns=[
        "date", "panel", "biomarker_canonical", "value",
        "unit", "lab_ref_low", "lab_ref_high", "source_lab", "notes",
    ])

# Compose dedupe key: (biomarker_canonical, date). Rows without a canonical
# key fall back to the raw biomarker label.
existing["_key"] = (
    existing["biomarker_canonical"].fillna("").astype(str).str.lower()
    + "|" + existing["date"].astype(str)
)
existing_keys = set(existing["_key"].tolist())

date_str = parsed["collection_date"].dropna().iloc[0] if (
    parsed["collection_date"].notna().any()
) else datetime.utcnow().strftime("%Y-%m-%d")

new_rows: list[dict] = []
skipped: list[dict] = []
unrecognized_imported: list[dict] = []
for _, r in parsed.iterrows():
    canonical = r.get("biomarker_canonical") or r["biomarker"]
    key = f"{str(canonical).lower()}|{date_str}"
    if key in existing_keys:
        skipped.append(r.to_dict())
        continue
    row = {
        "date": date_str,
        "panel": "function_health",
        "biomarker_canonical": canonical,
        "value": r["value"],
        "unit": r.get("unit"),
        "lab_ref_low": r.get("reference_low"),
        "lab_ref_high": r.get("reference_high"),
        "source_lab": "Function Health",
        "notes": ("unrecognized_name" if pd.isna(r.get("biomarker_canonical"))
                  else ""),
    }
    new_rows.append(row)
    existing_keys.add(key)
    if pd.isna(r.get("biomarker_canonical")):
        unrecognized_imported.append(row)

if new_rows:
    out = pd.concat(
        [existing.drop(columns=["_key"]), pd.DataFrame(new_rows)],
        ignore_index=True,
    )
else:
    out = existing.drop(columns=["_key"])

bw_path.parent.mkdir(parents=True, exist_ok=True)
out.to_csv(bw_path, index=False)

# Audit log row, mirroring the schema used by integrations / migrations.
log_row = pd.DataFrame([{
    "timestamp": datetime.now().isoformat(timespec="seconds"),
    "source_type": "function_health_pdf",
    "filename": upload.name,
    "rows_imported": len(new_rows),
    "rows_skipped_duplicate": len(skipped),
    "errors": "",
    "imported_by": "streamlit_function_health_import",
}])
if log_path.exists():
    log_row.to_csv(log_path, mode="a", header=False, index=False)
else:
    log_row.to_csv(log_path, mode="w", header=True, index=False)

# Clear cached data so other pages see the new rows immediately.
st.cache_data.clear()
refresh_data()


# ── Post-import summary ──────────────────────────────────────────────────────
st.success(
    f"Imported {len(new_rows)} new biomarker rows · "
    f"skipped {len(skipped)} duplicates · "
    f"{len(unrecognized_imported)} unrecognized name(s) imported as-is."
)

if unrecognized_imported:
    with st.expander("Unrecognized biomarker names (imported as-is)"):
        st.dataframe(
            pd.DataFrame(unrecognized_imported)[
                ["biomarker_canonical", "value", "unit"]
            ],
            use_container_width=True,
            hide_index=True,
        )

if skipped:
    with st.expander("Skipped as duplicates"):
        st.dataframe(
            pd.DataFrame(skipped)[
                ["biomarker", "biomarker_canonical", "value", "unit",
                 "collection_date"]
            ],
            use_container_width=True,
            hide_index=True,
        )
