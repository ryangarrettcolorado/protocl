"""Import Center — drag-and-drop CSV/Excel import with auto-mapping, validation, dedup."""
from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.data_loader import (
    load_data, refresh_data, append_row, DATA_DIR, DEFAULT_USER
)
from modules.charts import COLORS, metric_card_html
from modules.biomarker_aliases import ALIASES


st.set_page_config(page_title="Import Center · Protocōl", page_icon="⚗️", layout="wide")

from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_refresh = st.columns([6, 1])
with col_title:
    st.title("Import Center")
    st.caption("Bring data in — CSV / Excel upload with auto-mapping, validation, and dedup")
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()


# ────────────────────────────────────────────────────────────────────────────
# Source-type registry — each source declares its target table + schema
# ────────────────────────────────────────────────────────────────────────────
SOURCES = {
    "bloodwork": {
        "label": "Bloodwork (lab panel)",
        "filename": "bloodwork.csv",
        "key_columns": ["date", "biomarker_canonical"],   # dedup key
        "required": ["date", "biomarker_canonical", "value"],
        "schema": ["date", "panel", "biomarker_canonical", "value",
                   "unit", "lab_ref_low", "lab_ref_high", "source_lab", "notes"],
        "date_cols": ["date"],
        "long_format": True,    # one biomarker per row
        "description": (
            "One row per biomarker per draw. The `biomarker_canonical` column "
            "is auto-mapped from common lab aliases (LabCorp / Quest / Empire City). "
            "Wide-format files (one column per biomarker) can be melted in the next step."
        ),
    },
    "inbody": {
        "label": "InBody scan (body composition)",
        "filename": "inbody.csv",
        "key_columns": ["date"],
        "required": ["date", "weight_lbs"],
        "schema": ["date", "weight_lbs", "skeletal_muscle_mass_lbs",
                   "body_fat_mass_lbs", "body_fat_pct", "visceral_fat_level",
                   "lean_mass_lbs", "total_body_water_lbs", "bmr_kcal",
                   "source", "notes"],
        "date_cols": ["date"],
        "long_format": False,
        "description": "One row per scan. Maps common InBody export column names.",
    },
    "training": {
        "label": "Training activity (Strava / Garmin / TrainingPeaks)",
        "filename": "training.csv",
        "key_columns": ["date", "activity_type", "duration_min"],
        "required": ["date", "activity_type", "duration_min"],
        "schema": ["date", "activity_type", "source", "duration_min",
                   "distance_miles", "elevation_ft", "avg_hr_bpm", "max_hr_bpm",
                   "avg_power_watts", "avg_cadence_rpm", "calories", "tss",
                   "zone2_min", "notes"],
        "date_cols": ["date"],
        "long_format": False,
        "description": "One row per activity. Compatible with Strava / Garmin / TP exports.",
    },
    "wearables": {
        "label": "Wearable daily summary (Apple / Whoop / Oura)",
        "filename": "wearables.csv",
        "key_columns": ["date"],
        "required": ["date"],
        "schema": ["date", "resting_hr_bpm", "hrv_sdnn_ms", "vo2_max_ml_kg_min",
                   "sleep_duration_hrs", "sleep_deep_hrs", "sleep_rem_hrs",
                   "sleep_consistency_pct", "respiratory_rate_brpm", "spo2_pct",
                   "active_calories", "steps", "stand_hrs", "skin_temp_delta_f",
                   "source"],
        "date_cols": ["date"],
        "long_format": False,
        "description": "One row per day. Apple Health export, Whoop CSV, or Oura CSV.",
    },
    "cgm_readings": {
        "label": "CGM readings (Dexcom / Libre / Levels)",
        "filename": "cgm_readings.csv",
        "key_columns": ["datetime"],
        "required": ["datetime", "glucose_mg_dl"],
        "schema": ["datetime", "glucose_mg_dl", "glucose_mmol_l",
                   "source", "sensor_type", "notes"],
        "date_cols": ["datetime"],
        "long_format": False,
        "description": "One row per CGM reading (usually 5- or 15-minute intervals).",
    },
    "ketone_readings": {
        "label": "Ketone readings (Keto-Mojo / Lumen / strips)",
        "filename": "ketone_readings.csv",
        "key_columns": ["datetime"],
        "required": ["datetime", "blood_ketones_mmol_l"],
        "schema": ["datetime", "blood_ketones_mmol_l", "blood_glucose_mg_dl",
                   "gki", "source", "notes"],
        "date_cols": ["datetime"],
        "long_format": False,
        "description": "One row per blood-ketone test.",
    },
    "daily_log": {
        "label": "Daily log (nutrition + recovery)",
        "filename": "daily_log.csv",
        "key_columns": ["date"],
        "required": ["date"],
        "schema": ["date", "calories_kcal", "protein_g", "carbs_g", "fat_g",
                   "fiber_g", "water_oz", "sleep_hrs", "sleep_quality_1_10", "notes"],
        "date_cols": ["date"],
        "long_format": False,
        "description": "One row per day. From MacroFactor, Cronometer, or manual entry.",
    },
    "context_notes": {
        "label": "Context notes (travel, illness, deload, life events)",
        "filename": "context_notes.csv",
        "key_columns": ["date", "category", "note"],
        "required": ["date", "category", "note"],
        "schema": ["date", "category", "note"],
        "date_cols": ["date"],
        "long_format": False,
        "description": "One row per note. Used by Timeline + Recommendations pages.",
    },
}


# Reverse alias lookup — alias_lower -> canonical_key (for bloodwork)
ALIAS_LOOKUP: dict[str, str] = {}
for canon, aliases in ALIASES.items():
    ALIAS_LOOKUP[canon.lower()] = canon
    for a in aliases:
        ALIAS_LOOKUP[a.lower().strip()] = canon


def auto_map_columns(file_cols: list[str], target_cols: list[str]) -> dict[str, str]:
    """Best-effort mapping from uploaded column names to target schema columns.

    Strategy:
      1. Exact match (case-insensitive).
      2. Normalized match (strip non-alphanumerics, lowercase).
      3. Otherwise: empty / unmapped.
    """
    def norm(s: str) -> str:
        return "".join(c for c in s.lower() if c.isalnum())

    target_by_norm = {norm(t): t for t in target_cols}
    mapping: dict[str, str] = {}
    for fc in file_cols:
        # exact case-insensitive
        ci = fc.lower().strip()
        target_ci = {t.lower(): t for t in target_cols}
        if ci in target_ci:
            mapping[fc] = target_ci[ci]
            continue
        # normalized
        n = norm(fc)
        if n in target_by_norm:
            mapping[fc] = target_by_norm[n]
            continue
        mapping[fc] = ""
    return mapping


def parse_upload(uploaded) -> pd.DataFrame:
    """Read uploaded file as DataFrame — supports CSV, TSV, XLSX."""
    name = uploaded.name.lower()
    raw = uploaded.read()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))
    if name.endswith(".tsv"):
        return pd.read_csv(io.BytesIO(raw), sep="\t")
    # default CSV; try utf-8 then latin-1
    for enc in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(io.BytesIO(raw), encoding_errors="replace")


def melt_bloodwork_wide(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    """Convert a wide-format lab CSV (one column per biomarker) to long format."""
    df = df.copy()
    value_cols = [c for c in df.columns if c != date_col]
    long = df.melt(id_vars=[date_col], value_vars=value_cols,
                   var_name="biomarker_raw", value_name="value")
    # map raw -> canonical
    long["biomarker_canonical"] = long["biomarker_raw"].apply(
        lambda s: ALIAS_LOOKUP.get(str(s).lower().strip(), str(s).lower().strip())
    )
    long = long.rename(columns={date_col: "date"})
    # drop rows with no value
    long = long.dropna(subset=["value"])
    long["panel"] = ""
    long["unit"] = ""
    long["lab_ref_low"] = pd.NA
    long["lab_ref_high"] = pd.NA
    long["source_lab"] = "imported"
    long["notes"] = ""
    return long[["date", "panel", "biomarker_canonical", "value",
                  "unit", "lab_ref_low", "lab_ref_high", "source_lab", "notes"]]


def log_import(source_type: str, filename: str, n_imported: int,
                n_skipped: int, errors: str) -> None:
    """Append a row to import_log.csv."""
    append_row("import_log.csv", {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_type": source_type,
        "filename": filename,
        "rows_imported": n_imported,
        "rows_skipped_duplicate": n_skipped,
        "errors": errors,
        "imported_by": "manual_ui",
    })


# ────────────────────────────────────────────────────────────────────────────
# KPI cards — how much data is in here
# ────────────────────────────────────────────────────────────────────────────
data = load_data()
log_df = data.import_log.copy() if hasattr(data, "import_log") else pd.DataFrame()
TODAY = pd.Timestamp("2026-05-25")

last_import = "—"
if not log_df.empty and "timestamp" in log_df.columns:
    ts = pd.to_datetime(log_df["timestamp"], errors="coerce").max()
    if pd.notna(ts):
        last_import = ts.strftime("%b %d")

kpis = [
    ("SOURCES",        f"{len(SOURCES)}",                "supported", None),
    ("BLOODWORK ROWS", f"{len(data.bloodwork)}",          "biomarker × draw", None),
    ("WEARABLE DAYS",  f"{len(data.wearables)}",          "rows", None),
    ("TRAINING ROWS",  f"{len(data.training)}",           "activities", None),
    ("IMPORTS LOGGED", f"{len(log_df)}",                  "all-time", None),
    ("LAST IMPORT",    last_import,                        "most recent", None),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("")

# ────────────────────────────────────────────────────────────────────────────
# Tabs
# ────────────────────────────────────────────────────────────────────────────
tab_upload, tab_templates, tab_log, tab_about = st.tabs(
    ["📥 Upload", "📄 Templates", "📜 Import log", "ℹ️ About"]
)

# ── Tab 1: Upload flow ──────────────────────────────────────────────────────
with tab_upload:
    st.subheader("1 · Choose source type")
    src_keys = list(SOURCES.keys())
    src_key = st.selectbox(
        "Source",
        options=src_keys,
        format_func=lambda k: SOURCES[k]["label"],
        index=0,
    )
    src = SOURCES[src_key]
    st.caption(src["description"])

    st.subheader("2 · Upload file")
    upload = st.file_uploader(
        "CSV, TSV, or Excel — drop a file or click to browse",
        type=["csv", "tsv", "xlsx", "xls"],
        accept_multiple_files=False,
        key=f"upload_{src_key}",
    )

    if upload is not None:
        try:
            raw_df = parse_upload(upload)
        except Exception as e:
            st.error(f"Failed to parse file: {e}")
            st.stop()

        st.success(f"Read **{len(raw_df)}** rows × **{len(raw_df.columns)}** columns from `{upload.name}`")

        with st.expander("Preview raw upload", expanded=False):
            st.dataframe(raw_df.head(20), use_container_width=True, hide_index=True)

        # ── Bloodwork wide-format toggle ────────────────────────────────────
        is_wide = False
        if src_key == "bloodwork":
            non_date_cols = [c for c in raw_df.columns if c.lower() not in ("date", "draw_date", "collection_date")]
            looks_wide = (
                len(non_date_cols) > 5
                and any(c.lower() in ("date", "draw_date", "collection_date") for c in raw_df.columns)
                and "biomarker_canonical" not in raw_df.columns
                and "biomarker" not in raw_df.columns
            )
            if looks_wide:
                st.info(
                    "This looks like a **wide-format** lab CSV (one column per biomarker). "
                    "Protocōl can auto-melt it into long format and map biomarker names "
                    "via the alias dictionary."
                )
            is_wide = st.checkbox(
                "Treat as wide-format lab CSV (one column per biomarker)",
                value=looks_wide,
                key="wide_toggle",
            )

            if is_wide:
                date_col = st.selectbox(
                    "Which column holds the draw date?",
                    options=[c for c in raw_df.columns],
                    index=next(
                        (i for i, c in enumerate(raw_df.columns)
                         if c.lower() in ("date", "draw_date", "collection_date")), 0,
                    ),
                )
                raw_df = melt_bloodwork_wide(raw_df, date_col)
                st.success(f"Melted into long format — **{len(raw_df)}** biomarker-rows after dropping nulls.")
                with st.expander("Preview after melt + alias mapping"):
                    st.dataframe(raw_df.head(30), use_container_width=True, hide_index=True)

        # ── Column mapping ─────────────────────────────────────────────────
        st.subheader("3 · Map columns to schema")
        st.caption(f"Target schema: `{', '.join(src['schema'])}`")

        auto = auto_map_columns(list(raw_df.columns), src["schema"])
        target_options = [""] + src["schema"]
        mapping: dict[str, str] = {}
        map_cols = st.columns(3)
        for i, fc in enumerate(raw_df.columns):
            with map_cols[i % 3]:
                default = auto.get(fc, "")
                idx = target_options.index(default) if default in target_options else 0
                mapping[fc] = st.selectbox(
                    f"`{fc}` →",
                    options=target_options,
                    index=idx,
                    key=f"map_{src_key}_{fc}",
                )

        # Apply mapping
        used = {fc: tc for fc, tc in mapping.items() if tc}
        if not used:
            st.warning("No columns mapped yet — pick at least the required ones above.")
            st.stop()

        mapped_df = raw_df[list(used.keys())].rename(columns=used)

        # Parse dates
        for dc in src["date_cols"]:
            if dc in mapped_df.columns:
                mapped_df[dc] = pd.to_datetime(mapped_df[dc], errors="coerce")

        # ── Validation ─────────────────────────────────────────────────────
        st.subheader("4 · Validate")
        errors: list[str] = []
        missing_required = [r for r in src["required"] if r not in mapped_df.columns]
        if missing_required:
            errors.append(f"Missing required columns: {', '.join(missing_required)}")
        # null check on required
        for r in src["required"]:
            if r in mapped_df.columns:
                n_null = mapped_df[r].isna().sum()
                if n_null > 0:
                    errors.append(f"`{r}` has {n_null} null value(s)")
        # date parse failures
        for dc in src["date_cols"]:
            if dc in mapped_df.columns:
                n_bad = mapped_df[dc].isna().sum()
                if n_bad > 0:
                    errors.append(f"`{dc}` has {n_bad} unparseable date(s)")

        # ── Dedup vs existing ──────────────────────────────────────────────
        existing_path = DATA_DIR / DEFAULT_USER / src["filename"]
        existing = pd.read_csv(existing_path) if existing_path.exists() else pd.DataFrame()
        n_dupe = 0
        if not existing.empty and all(k in mapped_df.columns and k in existing.columns
                                       for k in src["key_columns"]):
            # parse dates on existing too
            for dc in src["date_cols"]:
                if dc in existing.columns:
                    existing[dc] = pd.to_datetime(existing[dc], errors="coerce")
            keys = src["key_columns"]
            # cast for comparison
            for k in keys:
                mapped_df[k] = mapped_df[k].astype(str)
                existing[k] = existing[k].astype(str)
            dupes_mask = mapped_df[keys].apply(tuple, axis=1).isin(
                existing[keys].apply(tuple, axis=1)
            )
            n_dupe = int(dupes_mask.sum())
            new_rows = mapped_df[~dupes_mask].copy()
        else:
            new_rows = mapped_df.copy()

        val_cols = st.columns(4)
        with val_cols[0]:
            st.markdown(metric_card_html("INPUT ROWS", f"{len(mapped_df)}", "after mapping", None),
                        unsafe_allow_html=True)
        with val_cols[1]:
            st.markdown(metric_card_html("NEW", f"{len(new_rows)}", "will be added",
                                          len(new_rows) > 0), unsafe_allow_html=True)
        with val_cols[2]:
            st.markdown(metric_card_html("DUPLICATES", f"{n_dupe}", "will skip",
                                          n_dupe == 0), unsafe_allow_html=True)
        with val_cols[3]:
            st.markdown(metric_card_html("ERRORS", f"{len(errors)}", "blockers",
                                          len(errors) == 0), unsafe_allow_html=True)

        if errors:
            for e in errors:
                st.error(e)
        else:
            st.success("All validations passed.")

        with st.expander("Preview rows to be imported", expanded=False):
            st.dataframe(new_rows.head(30), use_container_width=True, hide_index=True)

        # ── Commit ─────────────────────────────────────────────────────────
        st.subheader("5 · Commit")
        confirm = st.checkbox(
            f"I've reviewed the {len(new_rows)} new rows and want to append to "
            f"`data/{DEFAULT_USER}/{src['filename']}`",
            disabled=(len(new_rows) == 0 or len(errors) > 0),
        )
        if st.button(
            "✅ Import now",
            disabled=(not confirm or len(new_rows) == 0 or len(errors) > 0),
            type="primary",
            use_container_width=True,
        ):
            # Reorder to schema, fill missing schema cols with NA
            for c in src["schema"]:
                if c not in new_rows.columns:
                    new_rows[c] = pd.NA
            out = new_rows[src["schema"]]

            # Append
            if existing_path.exists():
                out.to_csv(existing_path, mode="a", header=False, index=False)
            else:
                existing_path.parent.mkdir(parents=True, exist_ok=True)
                out.to_csv(existing_path, mode="w", header=True, index=False)

            log_import(src_key, upload.name, len(out), n_dupe, "")
            st.cache_data.clear()
            st.success(
                f"Imported **{len(out)}** rows into `{src['filename']}` "
                f"(skipped {n_dupe} duplicates)."
            )
            st.balloons()


# ── Tab 2: Templates ────────────────────────────────────────────────────────
with tab_templates:
    st.subheader("Download a template")
    st.caption("Empty CSV with the exact column order Protocōl expects.")

    tcols = st.columns(2)
    for i, (key, src) in enumerate(SOURCES.items()):
        with tcols[i % 2]:
            st.markdown(f"**{src['label']}**")
            st.caption(", ".join(src["schema"]))
            template = pd.DataFrame(columns=src["schema"])
            csv = template.to_csv(index=False)
            st.download_button(
                f"⬇ {src['filename']}",
                data=csv,
                file_name=f"protocol_template_{src['filename']}",
                mime="text/csv",
                use_container_width=True,
                key=f"tmpl_{key}",
            )
            st.markdown("")


# ── Tab 3: Import log ───────────────────────────────────────────────────────
with tab_log:
    if log_df.empty:
        st.info("No imports logged yet. Every successful upload writes a row here.")
    else:
        show = log_df.sort_values("timestamp", ascending=False).copy()
        st.dataframe(show, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇ Download import log",
            data=show.to_csv(index=False),
            file_name="protocol_import_log.csv",
            mime="text/csv",
            use_container_width=True,
        )


# ── Tab 4: About ────────────────────────────────────────────────────────────
with tab_about:
    st.markdown("""
**What this is.** The single entry point for getting your own data into
Protocōl. Eight source types are supported out of the box, each with:

1. **Auto-mapping** from common export column names (LabCorp, Quest, Strava,
   Garmin, Apple Health, Whoop, Oura, Dexcom, Libre, MacroFactor, etc.).
2. **Wide-format unmelting** for lab CSVs that put one biomarker per column.
3. **Alias resolution** — biomarker names get normalized via
   `modules/biomarker_aliases.py` (e.g. `LDL-C` → `ldl_c_mg_dl`).
4. **Validation** — required-column check, null check, date-parse check.
5. **Dedup against existing data** using source-specific keys
   (`date + biomarker_canonical` for bloodwork, `date` for daily summaries).
6. **Atomic append** to the user's data directory, with an entry in
   `import_log.csv` for every successful run.

**Where data goes.** Every import writes to `data/<user_id>/<filename>.csv`.
In Phase 2, the same writer will commit to the user's GitHub repo via the
`modules/github_sync.py` helper.

**What's next.**
- **Apple HealthKit** direct pull (scaffold in `modules/ingest/healthkit.py`)
- **Whoop / Oura** OAuth pulls (scaffolds in `modules/ingest/`)
- **TrueNAS S3** mirror for raw lab PDFs
- **Email-in** address for forwarding lab PDFs that get OCR'd to bloodwork rows
    """)
