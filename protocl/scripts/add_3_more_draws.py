"""
Append 3 new LabCorp blood draws to bloodwork.csv:
  - 2025-03-14 (Labtest3.pdf)
  - 2024-12-05 (Labtest4.pdf)
  - 2024-08-26 (Labtest5.pdf — PRE-TRT BASELINE)

Skips Labtest1 (09/30/2025) + Labtest2 (06/20/2025) — already loaded.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime

BLOOD_CSV = Path("/home/user/workspace/protocl/protocl/data/ryan/bloodwork.csv")
NOTES_CSV = Path("/home/user/workspace/protocl/protocl/data/ryan/context_notes.csv")
LOG_CSV   = Path("/home/user/workspace/protocl/protocl/data/ryan/import_log.csv")
SOURCE_LAB = "LabCorp Denver"

# Canonical schema: (panel, key, unit, ref_low, ref_high)
# Reference ranges match existing draws unless noted. Free T ref differs for 2024-08-26.
SCHEMA = {
    "hematology": {
        "wbc_k_ul":            ("x10E3/uL", 3.4, 10.8),
        "rbc_m_ul":            ("x10E6/uL", 4.14, 5.8),
        "hemoglobin_g_dl":     ("g/dL", 13.0, 17.7),
        "hematocrit_pct":      ("%", 37.5, 51.0),
        "mcv_fl":              ("fL", 79.0, 97.0),
        "mch_pg":              ("pg", 26.6, 33.0),
        "mchc_g_dl":           ("g/dL", 31.5, 35.7),
        "rdw_pct":             ("%", 11.6, 15.4),
        "platelets_k_ul":      ("x10E3/uL", 150.0, 450.0),
        "neutrophils_pct":     ("%", None, None),
        "lymphocytes_pct":     ("%", None, None),
        "monocytes_pct":       ("%", None, None),
        "eosinophils_pct":     ("%", None, None),
        "basophils_pct":       ("%", None, None),
        "neutrophils_abs_k_ul":("x10E3/uL", 1.4, 7.0),
        "lymphocytes_abs_k_ul":("x10E3/uL", 0.7, 3.1),
    },
    "kidney": {
        "glucose_mg_dl":         ("mg/dL", 70.0, 99.0),
        "bun_mg_dl":             ("mg/dL", 6.0, 24.0),
        "creatinine_mg_dl":      ("mg/dL", 0.76, 1.27),
        "egfr_ml_min":           ("mL/min/1.73", 59.0, None),
        "bun_creatinine_ratio":  ("ratio", 9.0, 20.0),
        "sodium_mmol_l":         ("mmol/L", 134.0, 144.0),
        "potassium_mmol_l":      ("mmol/L", 3.5, 5.2),
        "chloride_mmol_l":       ("mmol/L", 96.0, 106.0),
        "co2_mmol_l":            ("mmol/L", 20.0, 29.0),
        "calcium_mg_dl":         ("mg/dL", 8.7, 10.2),
    },
    "liver": {
        "total_protein_g_dl":    ("g/dL", 6.0, 8.5),
        "albumin_g_dl":          ("g/dL", 4.1, 5.1),
        "globulin_g_dl":         ("g/dL", 1.5, 4.5),
        "total_bilirubin_mg_dl": ("mg/dL", 0.0, 1.2),
        "alp_u_l":               ("IU/L", 47.0, 123.0),
        "ast_u_l":               ("IU/L", 0.0, 40.0),
        "alt_u_l":               ("IU/L", 0.0, 44.0),
    },
    "lipids": {
        "total_cholesterol_mg_dl": ("mg/dL", 100.0, 199.0),
        "triglycerides_mg_dl":     ("mg/dL", 0.0, 149.0),
        "hdl_c_mg_dl":             ("mg/dL", 39.0, None),
        "vldl_c_mg_dl":            ("mg/dL", 5.0, 40.0),
        "ldl_c_mg_dl":             ("mg/dL", 0.0, 99.0),
    },
    "hormones": {
        "testosterone_total_ng_dl": ("ng/dL", 264.0, 916.0),
        "shbg_nmol_l":              ("nmol/L", 16.5, 55.9),
        "testosterone_free_pg_ml":  ("pg/mL", 30.3, 183.2),
        "dhea_s_ug_dl":             ("ug/dL", 102.6, 416.3),
        "lh_miu_ml":                ("mIU/mL", 1.7, 8.6),
        "prolactin_ng_ml":          ("ng/mL", 3.9, 22.7),
        "estradiol_pg_ml":          ("pg/mL", 7.6, 42.6),
        "psa_ng_ml":                ("ng/mL", 0.0, 4.0),
    },
    "thyroid": {
        "tsh_uiu_ml":     ("uIU/mL", 0.45, 4.5),
        "free_t3_pg_ml":  ("pg/mL", 2.0, 4.4),
        "free_t4_ng_dl":  ("ng/dL", 0.82, 1.77),
    },
    "glucose_insulin": {
        "hba1c_pct":             ("%", 4.8, 5.6),
        "fasting_insulin_uiu_ml":("uIU/mL", 2.6, 24.9),
    },
    "vitamins_minerals": {
        "vitamin_d_ng_ml": ("ng/mL", 30.0, 100.0),
    },
    "inflammation": {
        "hscrp_mg_l": ("mg/L", 0.0, 3.0),
    },
}

# === Per-draw values ===
# Format: panel -> key -> (value, note_or_None)
# None value = skip this row (e.g. Free T uncalc'd 2025-03-14)

DRAW_2025_03_14 = {
    "hematology": {
        "wbc_k_ul": (6.4, None), "rbc_m_ul": (5.72, None),
        "hemoglobin_g_dl": (16.8, None), "hematocrit_pct": (51.9, "HIGH"),
        "mcv_fl": (91.0, None), "mch_pg": (29.4, None), "mchc_g_dl": (32.4, None),
        "rdw_pct": (13.1, None), "platelets_k_ul": (259.0, None),
        "neutrophils_pct": (54.0, None), "lymphocytes_pct": (31.0, None),
        "monocytes_pct": (13.0, None), "eosinophils_pct": (1.0, None),
        "basophils_pct": (1.0, None),
        "neutrophils_abs_k_ul": (3.4, None), "lymphocytes_abs_k_ul": (2.0, None),
    },
    "kidney": {
        "glucose_mg_dl": (75.0, None), "bun_mg_dl": (14.0, None),
        "creatinine_mg_dl": (1.15, None), "egfr_ml_min": (82.0, None),
        "bun_creatinine_ratio": (12.0, None),
        "sodium_mmol_l": (139.0, None), "potassium_mmol_l": (3.9, None),
        "chloride_mmol_l": (101.0, None), "co2_mmol_l": (23.0, None),
        "calcium_mg_dl": (9.1, None),
    },
    "liver": {
        "total_protein_g_dl": (6.5, None), "albumin_g_dl": (4.5, None),
        "globulin_g_dl": (2.0, None), "total_bilirubin_mg_dl": (0.6, None),
        "alp_u_l": (50.0, None), "ast_u_l": (41.0, "HIGH"), "alt_u_l": (42.0, None),
    },
    "lipids": {
        "total_cholesterol_mg_dl": (135.0, None), "triglycerides_mg_dl": (66.0, None),
        "hdl_c_mg_dl": (34.0, "LOW"), "vldl_c_mg_dl": (14.0, None),
        "ldl_c_mg_dl": (87.0, None),
    },
    "hormones": {
        "testosterone_total_ng_dl": (1500.0, "Reported as >1500 (above detection ceiling)"),
        "shbg_nmol_l": (34.9, None),
        # Free T skipped — PDF: "Unable to calculate result since non-numeric"
        "dhea_s_ug_dl": (344.0, None),
        "lh_miu_ml": (0.3, "Reported as <0.3 (below detection floor) — TRT suppression"),
        "prolactin_ng_ml": (9.0, None),
        "estradiol_pg_ml": (103.0, "HIGH"),
        "psa_ng_ml": (1.9, None),
    },
    "thyroid": {
        "tsh_uiu_ml": (2.120, None), "free_t3_pg_ml": (3.5, None),
        "free_t4_ng_dl": (1.34, None),
    },
    "glucose_insulin": {
        "hba1c_pct": (5.3, None), "fasting_insulin_uiu_ml": (2.0, "LOW"),
    },
    "vitamins_minerals": {"vitamin_d_ng_ml": (118.0, "HIGH")},
    "inflammation": {"hscrp_mg_l": (1.37, None)},
}

DRAW_2024_12_05 = {
    "hematology": {
        "wbc_k_ul": (7.2, None), "rbc_m_ul": (6.12, "HIGH"),
        "hemoglobin_g_dl": (18.0, "HIGH"), "hematocrit_pct": (55.4, "HIGH"),
        "mcv_fl": (91.0, None), "mch_pg": (29.4, None), "mchc_g_dl": (32.5, None),
        "rdw_pct": (12.3, None), "platelets_k_ul": (264.0, None),
        "neutrophils_pct": (56.0, None), "lymphocytes_pct": (29.0, None),
        "monocytes_pct": (12.0, None), "eosinophils_pct": (1.0, None),
        "basophils_pct": (1.0, None),
        "neutrophils_abs_k_ul": (4.0, None), "lymphocytes_abs_k_ul": (2.1, None),
    },
    "kidney": {
        "glucose_mg_dl": (93.0, None), "bun_mg_dl": (15.0, None),
        "creatinine_mg_dl": (1.30, "HIGH"), "egfr_ml_min": (71.0, None),
        "bun_creatinine_ratio": (12.0, None),
        "sodium_mmol_l": (143.0, None), "potassium_mmol_l": (4.2, None),
        "chloride_mmol_l": (104.0, None), "co2_mmol_l": (21.0, None),
        "calcium_mg_dl": (9.2, None),
    },
    "liver": {
        "total_protein_g_dl": (6.7, None), "albumin_g_dl": (4.4, None),
        "globulin_g_dl": (2.3, None), "total_bilirubin_mg_dl": (0.3, None),
        "alp_u_l": (61.0, None), "ast_u_l": (38.0, None), "alt_u_l": (35.0, None),
    },
    "lipids": {
        "total_cholesterol_mg_dl": (144.0, None), "triglycerides_mg_dl": (47.0, None),
        "hdl_c_mg_dl": (43.0, None), "vldl_c_mg_dl": (10.0, None),
        "ldl_c_mg_dl": (91.0, None),
    },
    "hormones": {
        "testosterone_total_ng_dl": (1020.0, "HIGH"),
        "shbg_nmol_l": (38.5, None),
        "testosterone_free_pg_ml": (223.4, "HIGH"),
        "dhea_s_ug_dl": (248.0, None),
        "lh_miu_ml": (0.3, "Reported as <0.3 (below detection floor) — TRT suppression"),
        "prolactin_ng_ml": (8.1, None),
        "estradiol_pg_ml": (51.3, "HIGH"),
        "psa_ng_ml": (1.0, None),
    },
    "thyroid": {
        "tsh_uiu_ml": (1.880, None), "free_t3_pg_ml": (3.7, None),
        "free_t4_ng_dl": (1.15, None),
    },
    "glucose_insulin": {
        "hba1c_pct": (5.3, None), "fasting_insulin_uiu_ml": (4.9, None),
    },
    "vitamins_minerals": {"vitamin_d_ng_ml": (80.2, None)},
    "inflammation": {"hscrp_mg_l": (2.76, None)},
}

# Pre-TRT baseline — Free T ref range differs (42.3-190.0)
DRAW_2024_08_26 = {
    "hematology": {
        "wbc_k_ul": (6.1, None), "rbc_m_ul": (5.19, None),
        "hemoglobin_g_dl": (15.5, None), "hematocrit_pct": (44.6, None),
        "mcv_fl": (86.0, None), "mch_pg": (29.9, None), "mchc_g_dl": (34.8, None),
        "rdw_pct": (12.0, None), "platelets_k_ul": (251.0, None),
        "neutrophils_pct": (53.0, None), "lymphocytes_pct": (34.0, None),
        "monocytes_pct": (11.0, None), "eosinophils_pct": (1.0, None),
        "basophils_pct": (1.0, None),
        "neutrophils_abs_k_ul": (3.3, None), "lymphocytes_abs_k_ul": (2.0, None),
    },
    "kidney": {
        "glucose_mg_dl": (89.0, None), "bun_mg_dl": (19.0, None),
        "creatinine_mg_dl": (1.04, None), "egfr_ml_min": (93.0, None),
        "bun_creatinine_ratio": (18.0, None),
        "sodium_mmol_l": (140.0, None), "potassium_mmol_l": (4.2, None),
        "chloride_mmol_l": (106.0, None), "co2_mmol_l": (20.0, None),
        "calcium_mg_dl": (9.8, None),
    },
    "liver": {
        "total_protein_g_dl": (6.7, None), "albumin_g_dl": (4.8, None),
        "globulin_g_dl": (1.9, None), "total_bilirubin_mg_dl": (0.9, None),
        "alp_u_l": (57.0, None), "ast_u_l": (38.0, None), "alt_u_l": (38.0, None),
    },
    "lipids": {
        "total_cholesterol_mg_dl": (168.0, None), "triglycerides_mg_dl": (69.0, None),
        "hdl_c_mg_dl": (57.0, None), "vldl_c_mg_dl": (13.0, None),
        "ldl_c_mg_dl": (98.0, None),
    },
    "hormones": {
        "testosterone_total_ng_dl": (434.0, "Pre-TRT baseline (natural production)"),
        "shbg_nmol_l": (43.8, None),
        "testosterone_free_pg_ml": (70.9, None),  # ref 42.3-190.0 — override below
        "dhea_s_ug_dl": (150.0, None),
        "lh_miu_ml": (3.6, "Natural LH (pre-TRT)"),
        "prolactin_ng_ml": (9.0, None),
        "estradiol_pg_ml": (27.0, None),
        "psa_ng_ml": (1.1, None),
    },
    "thyroid": {
        "tsh_uiu_ml": (1.250, None), "free_t3_pg_ml": (3.0, None),
        "free_t4_ng_dl": (1.24, None),
    },
    "glucose_insulin": {
        "hba1c_pct": (5.3, None), "fasting_insulin_uiu_ml": (1.3, "LOW"),
    },
    "vitamins_minerals": {"vitamin_d_ng_ml": (39.7, None)},
    "inflammation": {"hscrp_mg_l": (3.13, "HIGH")},
}

# Per-draw range overrides (when LabCorp shipped a different reference interval)
RANGE_OVERRIDES = {
    "2024-08-26": {
        "testosterone_free_pg_ml": (42.3, 190.0),  # older ref range
    },
}


def build_rows(date_str, draw):
    rows = []
    overrides = RANGE_OVERRIDES.get(date_str, {})
    for panel, markers in draw.items():
        for key, (value, note) in markers.items():
            if value is None:
                continue
            unit, ref_lo, ref_hi = SCHEMA[panel][key]
            if key in overrides:
                ref_lo, ref_hi = overrides[key]
            rows.append({
                "date": date_str,
                "panel": panel,
                "biomarker_canonical": key,
                "value": value,
                "unit": unit,
                "lab_ref_low": ref_lo if ref_lo is not None else "",
                "lab_ref_high": ref_hi if ref_hi is not None else "",
                "source_lab": SOURCE_LAB,
                "notes": note or "",
            })
    return rows


def main():
    existing = pd.read_csv(BLOOD_CSV)
    print(f"Existing rows: {len(existing)} (dates: {sorted(existing['date'].unique())})")

    new_rows = []
    new_rows += build_rows("2025-03-14", DRAW_2025_03_14)
    new_rows += build_rows("2024-12-05", DRAW_2024_12_05)
    new_rows += build_rows("2024-08-26", DRAW_2024_08_26)

    new_df = pd.DataFrame(new_rows)
    print(f"New rows: {len(new_df)} ({new_df['date'].value_counts().to_dict()})")

    combined = pd.concat([existing, new_df], ignore_index=True)
    combined = combined.sort_values(["date", "panel", "biomarker_canonical"]).reset_index(drop=True)
    combined.to_csv(BLOOD_CSV, index=False)
    print(f"Wrote {len(combined)} rows → {BLOOD_CSV}")
    print(f"All dates: {sorted(combined['date'].unique())}")

    # Append context note for 2025-03-14 Free T uncalc'd (schema: date,category,note)
    note_row = {
        "date": "2025-03-14",
        "category": "lab",
        "note": "Free Testosterone unable to calculate (LabCorp Direct: total T reported as >1500 ng/dL, above detection ceiling — SHBG-based calculation requires numeric total T). E2 spiked to 103 pg/mL (HIGH); anastrozole adjustment likely followed.",
    }
    if NOTES_CSV.exists():
        notes = pd.read_csv(NOTES_CSV)
        notes = pd.concat([notes, pd.DataFrame([note_row])], ignore_index=True)
        notes.to_csv(NOTES_CSV, index=False)
        print(f"Appended context note → {NOTES_CSV}")

    # Append import_log audit rows (schema: timestamp,source_type,filename,rows_imported,rows_skipped_duplicate,errors,imported_by)
    ts = datetime.now().isoformat(timespec="seconds")
    log_rows = [
        {"timestamp": ts, "source_type": "bloodwork_pdf", "filename": "Labtest3.pdf",
         "rows_imported": len([r for r in new_rows if r["date"] == "2025-03-14"]),
         "rows_skipped_duplicate": 0, "errors": "", "imported_by": "add_3_more_draws.py"},
        {"timestamp": ts, "source_type": "bloodwork_pdf", "filename": "Labtest4.pdf",
         "rows_imported": len([r for r in new_rows if r["date"] == "2024-12-05"]),
         "rows_skipped_duplicate": 0, "errors": "", "imported_by": "add_3_more_draws.py"},
        {"timestamp": ts, "source_type": "bloodwork_pdf", "filename": "Labtest5.pdf",
         "rows_imported": len([r for r in new_rows if r["date"] == "2024-08-26"]),
         "rows_skipped_duplicate": 0, "errors": "", "imported_by": "add_3_more_draws.py"},
        {"timestamp": ts, "source_type": "bloodwork_pdf", "filename": "Labtest1.pdf",
         "rows_imported": 0, "rows_skipped_duplicate": 53, "errors": "",
         "imported_by": "add_3_more_draws.py"},
        {"timestamp": ts, "source_type": "bloodwork_pdf", "filename": "Labtest2.pdf",
         "rows_imported": 0, "rows_skipped_duplicate": 53, "errors": "",
         "imported_by": "add_3_more_draws.py"},
    ]
    if LOG_CSV.exists():
        log = pd.read_csv(LOG_CSV)
        log = pd.concat([log, pd.DataFrame(log_rows)], ignore_index=True)
        log.to_csv(LOG_CSV, index=False)
        print(f"Appended {len(log_rows)} import_log rows → {LOG_CSV}")


if __name__ == "__main__":
    main()
