"""
One-shot migration: replace all dummy data in protocl/protocl/data/ryan/
with Ryan's real personal data.

Inputs (from /home/user/workspace/):
  - Ryan-Bloodtest.pdf (LabCorp, 2 draws: 2025-09-30 + 2025-06-20)
  - InBody-20260526.csv (19 rows, 2025-10-06 → 2026-05-23)
  - weekly_peptide_supplement_protocol_v3.md (full protocol)
  - ecg_2020-04-14.csv, ecg_2020-04-15.csv, ecg_2024-03-26.csv, ecg_2024-09-21.csv
  - 6 route_*.gpx files (Apple Health GPX exports)

Outputs (all under protocl/protocl/data/ryan/):
  - bloodwork.csv    — full panel from LabCorp PDF, both draws
  - inbody.csv       — 19 rows mapped to canonical schema
  - protocol.csv     — every compound from v3 protocol
  - training.csv     — GPX-derived rides (date, duration, distance, elev, source)
  - context_notes.csv — ECG sinus-rhythm entries + import note
  - import_log.csv   — append migration audit rows
  - All previous *.csv files renamed to *.demo.csv as a backup

Empty data sources kept untouched: cgm_readings.csv, ketone_readings.csv,
daily_log.csv, action_items.csv, wearables.csv, nof1_experiments.json
(wearables.csv is the placeholder for the missing export.zip).
"""
from __future__ import annotations

import csv
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd

# ────────────────────────────────────────────────────────────────────────────
# Paths
# ────────────────────────────────────────────────────────────────────────────
WS = Path("/home/user/workspace")
DATA_DIR = WS / "protocl/protocl/data/ryan"
TODAY = pd.Timestamp.today().normalize().strftime("%Y-%m-%d")

# ────────────────────────────────────────────────────────────────────────────
# Step 1: Back up existing demo files
# ────────────────────────────────────────────────────────────────────────────
DEMO_BACKUP_NAMES = [
    "bloodwork.csv", "inbody.csv", "protocol.csv", "training.csv",
    "context_notes.csv", "cgm_readings.csv", "ketone_readings.csv",
    "daily_log.csv", "action_items.csv", "wearables.csv",
]
print("=" * 70)
print("STEP 1: Back up demo data → *.demo.csv")
print("=" * 70)
for name in DEMO_BACKUP_NAMES:
    src = DATA_DIR / name
    dst = DATA_DIR / name.replace(".csv", ".demo.csv")
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
        print(f"  backed up {name} → {dst.name}")
    elif dst.exists():
        print(f"  skip (already backed up): {dst.name}")

# ────────────────────────────────────────────────────────────────────────────
# Step 2: Build bloodwork.csv from LabCorp PDF
#
# Two draws extracted by hand from the PDF (most accurate vs. OCR for tables):
#   2025-09-30 (current) and 2025-06-20 (previous)
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 2: Write bloodwork.csv")
print("=" * 70)

# Each entry: (panel, biomarker_canonical, unit, lab_low, lab_high, current_value, previous_value)
BLOOD = [
    # CBC With Differential/Platelet
    ("hematology", "wbc_k_ul",                 "x10E3/uL", 3.4,  10.8, 7.9,  6.4),
    ("hematology", "rbc_m_ul",                 "x10E6/uL", 4.14, 5.80, 5.93, 5.76),
    ("hematology", "hemoglobin_g_dl",          "g/dL",     13.0, 17.7, 17.9, 17.2),
    ("hematology", "hematocrit_pct",           "%",        37.5, 51.0, 54.3, 53.9),
    ("hematology", "mcv_fl",                   "fL",       79.0, 97.0, 92.0, 94.0),
    ("hematology", "mch_pg",                   "pg",       26.6, 33.0, 30.2, 29.9),
    ("hematology", "mchc_g_dl",                "g/dL",     31.5, 35.7, 33.0, 31.9),
    ("hematology", "rdw_pct",                  "%",        11.6, 15.4, 12.5, 13.2),
    ("hematology", "platelets_k_ul",           "x10E3/uL", 150,  450,  266,  258),
    ("hematology", "neutrophils_pct",          "%",        None, None, 62,   55),
    ("hematology", "lymphocytes_pct",          "%",        None, None, 27,   32),
    ("hematology", "monocytes_pct",            "%",        None, None, 9,    10),
    ("hematology", "eosinophils_pct",          "%",        None, None, 1,    1),
    ("hematology", "basophils_pct",            "%",        None, None, 1,    1),
    ("hematology", "neutrophils_abs_k_ul",     "x10E3/uL", 1.4,  7.0,  4.9,  3.6),
    ("hematology", "lymphocytes_abs_k_ul",     "x10E3/uL", 0.7,  3.1,  2.1,  2.1),
    # CMP
    ("kidney",     "glucose_mg_dl",            "mg/dL",    70,   99,   87,   84),
    ("kidney",     "bun_mg_dl",                "mg/dL",    6,    24,   15,   16),
    ("kidney",     "creatinine_mg_dl",         "mg/dL",    0.76, 1.27, 1.22, 1.23),
    ("kidney",     "egfr_ml_min",              "mL/min/1.73", 59, None, 76,  76),
    ("kidney",     "bun_creatinine_ratio",     "ratio",    9,    20,   12,   13),
    ("kidney",     "sodium_mmol_l",            "mmol/L",   134,  144,  137,  139),
    ("kidney",     "potassium_mmol_l",         "mmol/L",   3.5,  5.2,  4.0,  4.2),
    ("kidney",     "chloride_mmol_l",          "mmol/L",   96,   106,  99,   104),
    ("kidney",     "co2_mmol_l",               "mmol/L",   20,   29,   21,   21),  # low-elev ref
    ("kidney",     "calcium_mg_dl",            "mg/dL",    8.7,  10.2, 9.9,  9.0),
    ("liver",      "total_protein_g_dl",       "g/dL",     6.0,  8.5,  7.1,  6.4),
    ("liver",      "albumin_g_dl",             "g/dL",     4.1,  5.1,  4.8,  4.4),
    ("liver",      "globulin_g_dl",            "g/dL",     1.5,  4.5,  2.3,  2.0),
    ("liver",      "total_bilirubin_mg_dl",    "mg/dL",    0.0,  1.2,  0.7,  0.4),
    ("liver",      "alp_u_l",                  "IU/L",     47,   123,  56,   50),
    ("liver",      "ast_u_l",                  "IU/L",     0,    40,   33,   43),
    ("liver",      "alt_u_l",                  "IU/L",     0,    44,   32,   45),
    # Lipids
    ("lipids",     "total_cholesterol_mg_dl",  "mg/dL",    100,  199,  164,  146),
    ("lipids",     "triglycerides_mg_dl",      "mg/dL",    0,    149,  71,   62),
    ("lipids",     "hdl_c_mg_dl",              "mg/dL",    39,   None, 51,   51),
    ("lipids",     "vldl_c_mg_dl",             "mg/dL",    5,    40,   14,   13),
    ("lipids",     "ldl_c_mg_dl",              "mg/dL",    0,    99,   99,   82),
    # Hormones
    ("hormones",   "testosterone_total_ng_dl", "ng/dL",    264,  916,  1272, 1289),
    ("hormones",   "shbg_nmol_l",              "nmol/L",   16.5, 55.9, 36.4, 30.6),
    ("hormones",   "testosterone_free_pg_ml",  "pg/mL",    30.3, 183.2, 287.3, 339.0),
    # Thyroid
    ("thyroid",    "tsh_uiu_ml",               "uIU/mL",   0.450, 4.500, 1.920, 2.290),
    ("thyroid",    "free_t3_pg_ml",            "pg/mL",    2.0,  4.4,  3.8,  3.6),
    ("thyroid",    "free_t4_ng_dl",            "ng/dL",    0.82, 1.77, 1.17, 1.18),
    # Glucose / Insulin
    ("glucose_insulin", "hba1c_pct",           "%",        4.8,  5.6,  5.3,  5.3),
    ("glucose_insulin", "fasting_insulin_uiu_ml", "uIU/mL", 2.6, 24.9, 5.1,  7.4),
    # Hormones (extended)
    ("hormones",   "dhea_s_ug_dl",             "ug/dL",    102.6, 416.3, 493.0, 531.0),
    ("hormones",   "lh_miu_ml",                "mIU/mL",   1.7,  8.6,  0.3,  0.3),  # <0.3 → use 0.3
    ("hormones",   "prolactin_ng_ml",          "ng/mL",    3.9,  22.7, 5.8,  6.9),
    ("hormones",   "estradiol_pg_ml",          "pg/mL",    7.6,  42.6, 60.0, 14.5),
    ("hormones",   "psa_ng_ml",                "ng/mL",    0.0,  4.0,  1.7,  1.3),
    # Vitamins
    ("vitamins_minerals", "vitamin_d_ng_ml",   "ng/mL",    30.0, 100.0, 118.0, 114.0),
    # Inflammation
    ("inflammation", "hscrp_mg_l",             "mg/L",     0.00, 3.00, 1.40, 0.74),
]

bloodwork_rows = []
LAB = "LabCorp Denver"
for panel, marker, unit, lo, hi, current, previous in BLOOD:
    notes = ""
    if marker == "lh_miu_ml":
        notes = "Reported as <0.3 (below detection); stored as 0.3 floor"
    if marker == "co2_mmol_l":
        notes = "Low-elevation reference; high-elev (>3000 ft) male >6y: 17–26"
    bloodwork_rows.append({
        "date": "2025-09-30", "panel": panel, "biomarker_canonical": marker,
        "value": current, "unit": unit, "lab_ref_low": lo, "lab_ref_high": hi,
        "source_lab": LAB, "notes": notes,
    })
    if previous is not None:
        bloodwork_rows.append({
            "date": "2025-06-20", "panel": panel, "biomarker_canonical": marker,
            "value": previous, "unit": unit, "lab_ref_low": lo, "lab_ref_high": hi,
            "source_lab": LAB, "notes": notes,
        })

bw_df = pd.DataFrame(bloodwork_rows)
bw_df = bw_df.sort_values(["date", "panel", "biomarker_canonical"]).reset_index(drop=True)
bw_df.to_csv(DATA_DIR / "bloodwork.csv", index=False)
print(f"  wrote {len(bw_df)} rows to bloodwork.csv")
print(f"  draws: {sorted(bw_df['date'].unique().tolist())}")
print(f"  unique biomarkers: {bw_df['biomarker_canonical'].nunique()}")

# ────────────────────────────────────────────────────────────────────────────
# Step 3: InBody parse
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 3: Write inbody.csv")
print("=" * 70)

inbody_raw = pd.read_csv(WS / "InBody-20260526.csv", encoding="utf-8-sig")
# date column is YYYYMMDDHHMMSS — convert
inbody_raw["date"] = pd.to_datetime(inbody_raw["date"].astype(str), format="%Y%m%d%H%M%S")

# KJ → kcal: 1 kJ = 0.239006 kcal
inbody_rows = []
for _, r in inbody_raw.iterrows():
    inbody_rows.append({
        "date": r["date"].strftime("%Y-%m-%d"),
        "weight_lbs": round(float(r["Weight(lb)"]), 1),
        "skeletal_muscle_mass_lbs": round(float(r["Skeletal Muscle Mass(lb)"]), 1),
        "body_fat_mass_lbs": round(float(r["Body Fat Mass(lb)"]), 1),
        "body_fat_pct": round(float(r["Percent Body Fat(%)"]), 1),
        "visceral_fat_level": int(r["Visceral Fat Level(Level)"]),
        "lean_mass_lbs": round(float(r["Weight(lb)"]) - float(r["Body Fat Mass(lb)"]), 1),
        "total_body_water_lbs": round(float(r["Total Body Water(L)"]) * 2.20462, 1),  # L → lb (water ≈1 kg/L)
        "bmr_kcal": int(round(float(r["Basal Metabolic Rate(kJ)"]) * 0.239006)),
        "source": "InBody",
        "notes": f"InBody Score {int(r['InBody Score'])} · BMI {r['BMI(kg/m²)']}",
    })

inbody_df = pd.DataFrame(inbody_rows).sort_values("date").reset_index(drop=True)
inbody_df.to_csv(DATA_DIR / "inbody.csv", index=False)
print(f"  wrote {len(inbody_df)} rows to inbody.csv")
print(f"  range: {inbody_df['date'].min()} → {inbody_df['date'].max()}")
print(f"  weight: {inbody_df['weight_lbs'].max()} → {inbody_df['weight_lbs'].min()} lbs "
      f"(Δ {inbody_df['weight_lbs'].max() - inbody_df['weight_lbs'].min():.1f})")
print(f"  body fat %: {inbody_df['body_fat_pct'].max():.1f} → {inbody_df['body_fat_pct'].min():.1f}")

# ────────────────────────────────────────────────────────────────────────────
# Step 4: Protocol from the v3 markdown
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 4: Write protocol.csv")
print("=" * 70)

# Conservative start date for active items — same as protocol compile date
PROTOCOL_START = "2026-05-01"

PROTOCOL = [
    # ── Hormone Backbone ──
    {"name": "Testosterone Cypionate", "category": "hormone",
     "dose": 100, "unit": "mg", "frequency": "2x/week (Mon & Thu AM)",
     "route": "IM or subQ", "timing": "AM",
     "reason": "TRT — physiologic testosterone restoration", "prescriber": "Physician",
     "cycle_status": "active", "adherence_pct": 100,
     "notes": "200 mg/mL vial; 0.5 mL = 50 U per injection; 200 mg/week total"},
    {"name": "Retatrutide", "category": "peptide",
     "dose": 4, "unit": "mg", "frequency": "weekly (Sun PM)",
     "route": "subQ", "timing": "Evening",
     "reason": "Metabolic / GLP-1+GIP+GCG agonist", "prescriber": "Physician",
     "cycle_status": "active", "adherence_pct": 100,
     "notes": "12 mg + 3.0 mL BAC → 4 mg/mL; 1.0 mL = 100 U"},
    {"name": "Anastrozole", "category": "medication",
     "dose": 0.25, "unit": "mg", "frequency": "2x/week (Mon & Thu AM)",
     "route": "oral", "timing": "AM with TRT",
     "reason": "Estrogen control on TRT", "prescriber": "Physician",
     "cycle_status": "active", "adherence_pct": 100,
     "notes": "0.5 mg/week total"},
    {"name": "Oxandrolone (Anavar)", "category": "medication",
     "dose": 50, "unit": "mg", "frequency": "daily (split 25 AM + 25 pre-workout)",
     "route": "oral", "timing": "AM + pre-workout",
     "reason": "Anabolic / strength cycle", "prescriber": "Physician",
     "cycle_status": "active", "adherence_pct": 100,
     "notes": "No acetaminophen or alcohol on-cycle; mid-cycle liver panel"},

    # ── Morning oral supplements ──
    {"name": "Creatine Monohydrate", "category": "supplement",
     "dose": 10, "unit": "g", "frequency": "2x/day (AM + pre-workout)",
     "route": "oral", "timing": "AM + pre-workout",
     "reason": "Strength / power / cognitive", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "20 g/day loading; drop to 3–5 g/day maintenance after week 1"},
    {"name": "CoQ10", "category": "supplement",
     "dose": 100, "unit": "mg", "frequency": "2x/day (AM + pre-workout)",
     "route": "oral", "timing": "AM + pre-workout",
     "reason": "Mitochondrial / cardiovascular", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "200 mg/day split"},
    {"name": "PQQ", "category": "supplement",
     "dose": 20, "unit": "mg", "frequency": "2x/day (AM + midday)",
     "route": "oral", "timing": "AM + midday",
     "reason": "Mitochondrial biogenesis", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "40 mg/day split"},
    {"name": "Alpha GPC", "category": "supplement",
     "dose": 600, "unit": "mg", "frequency": "2x/day (AM + pre-workout)",
     "route": "oral", "timing": "AM + pre-workout",
     "reason": "Acetylcholine / cognitive / training drive", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "1,200 mg/day split"},
    {"name": "Micro Ingredients Saffron+ (10-in-1)", "category": "supplement",
     "dose": 1, "unit": "serving", "frequency": "daily",
     "route": "oral", "timing": "AM",
     "reason": "Mood / stress / Mg / turmeric / KSM-66", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "Contains magnesium — account for total Mg across stack"},
    {"name": "Grüns Adult Super Greens Gummies", "category": "supplement",
     "dose": 1, "unit": "serving", "frequency": "daily",
     "route": "oral", "timing": "AM",
     "reason": "Multivitamin / greens baseline", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "Contains Zn + Se — monitor overlap with bedtime stack"},
    {"name": "Vitamin D3 + K2 (MK-7)", "category": "supplement",
     "dose": 1, "unit": "serving", "frequency": "daily (sublingual)",
     "route": "sublingual", "timing": "AM fasted",
     "reason": "Free T optimization / bone / CV", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "D3 reduces SHBG; K2 directs calcium away from arteries"},
    {"name": "PartiQlar Pure NMN", "category": "supplement",
     "dose": 550, "unit": "mg", "frequency": "daily",
     "route": "oral", "timing": "AM fasted",
     "reason": "NAD+ precursor / cellular energy", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "Pairs with CoQ10 + PQQ + MOTS-c mitochondrial stack"},
    {"name": "Omega-3 Fish Oil (EPA+DHA)", "category": "supplement",
     "dose": 3.5, "unit": "g", "frequency": "daily",
     "route": "oral", "timing": "Largest meal",
     "reason": "HDL support / anti-inflammatory / recovery", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "Critical on Anavar cycle for HDL protection; TG-form preferred"},
    {"name": "Life Extension Pomegranate Fruit Extract", "category": "supplement",
     "dose": 500, "unit": "mg", "frequency": "daily",
     "route": "oral", "timing": "AM with meal",
     "reason": "Urolithin A precursor / mitophagy", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "Standardized to 30% punicalagins"},
    {"name": "Nature's Truth Boron Complex", "category": "supplement",
     "dose": 6, "unit": "mg", "frequency": "daily",
     "route": "oral", "timing": "AM with food",
     "reason": "Free T / SHBG reduction / bone", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "Triple-form citrate + glycinate + aspartate"},
    {"name": "Jarrow Taurine", "category": "supplement",
     "dose": 1000, "unit": "mg", "frequency": "2x/day (AM + pre-workout)",
     "route": "oral", "timing": "AM + pre-workout",
     "reason": "Cardiovascular / HDL protection / fatigue buffer", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "2 g/day total"},
    {"name": "Toniiq Berberine HCl 97%", "category": "supplement",
     "dose": 500, "unit": "mg", "frequency": "3x/day (before each meal)",
     "route": "oral", "timing": "Before B/L/D",
     "reason": "AMPK / glucose / lipid metabolism", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 85,
     "notes": "1,500 mg/day; avoid pre-workout timing"},
    {"name": "Double Wood TUDCA", "category": "supplement",
     "dose": 375, "unit": "mg", "frequency": "daily",
     "route": "oral", "timing": "AM with food",
     "reason": "Liver protection (on-cycle)", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "250–500 mg range; away from Anavar by 1–2 h"},
    {"name": "Jarrow NAC Sustain", "category": "supplement",
     "dose": 600, "unit": "mg", "frequency": "2x/day (midday + evening)",
     "route": "oral", "timing": "Midday + evening",
     "reason": "Glutathione precursor / liver antioxidant", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "1,200 mg/day total"},
    {"name": "Adapt Naturals 4-in-1 Biome Protect", "category": "supplement",
     "dose": 1, "unit": "serving", "frequency": "daily",
     "route": "oral", "timing": "Evening",
     "reason": "Pre/pro/postbiotics + polyphenols", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "Away from antibiotics if applicable"},
    {"name": "Adapt Naturals Magnesium Glycinate", "category": "supplement",
     "dose": 300, "unit": "mg", "frequency": "daily",
     "route": "oral", "timing": "Bedtime",
     "reason": "Sleep / muscle recovery", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 95,
     "notes": "Confirm total Mg stays within 350–400 mg/day across stack"},
    {"name": "Zinc + Selenium + Copper (Deal Supplement)", "category": "supplement",
     "dose": 1, "unit": "serving", "frequency": "daily",
     "route": "oral", "timing": "Bedtime",
     "reason": "Hormonal / immune / antioxidant", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 80,
     "notes": "⚠️ 50 mg Zn exceeds NIH UL of 40 mg/day — discuss with MD"},

    # ── Mon–Fri Peptides (AM) ──
    {"name": "Semax", "category": "peptide",
     "dose": 300, "unit": "mcg", "frequency": "Mon–Fri AM",
     "route": "subQ", "timing": "AM fasted",
     "reason": "Cognitive drive / focus", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "10 mg + 3 mL BAC → 9 U per dose; 10–20 day sprints with off weeks"},
    {"name": "Selank", "category": "peptide",
     "dose": 300, "unit": "mcg", "frequency": "Mon–Fri AM",
     "route": "subQ", "timing": "AM fasted",
     "reason": "Calm focus / anxiety control", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "10 mg + 3 mL BAC → 9 U per dose; 6–8 wk cycle / 2–4 wk off"},
    {"name": "MOTS-c", "category": "peptide",
     "dose": 400, "unit": "mcg", "frequency": "daily AM (weekend optional)",
     "route": "subQ", "timing": "AM fasted",
     "reason": "Metabolic / mitochondrial", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "10 mg + 3 mL BAC → 12 U per dose; 8–12 wk on / 4+ wk off"},
    {"name": "GHK-Cu", "category": "peptide",
     "dose": 1500, "unit": "mcg", "frequency": "Mon–Fri AM",
     "route": "subQ", "timing": "AM",
     "reason": "Systemic anti-aging / recovery", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 85,
     "notes": "Confirm mg/mL with pharmacy; 1–2 mg range; 6–8 wk on / 4 wk off"},

    # ── Daily Peptides (PM) ──
    {"name": "CJC-1295 (no DAC) + Ipamorelin", "category": "peptide",
     "dose": 600, "unit": "mcg", "frequency": "daily PM (weekend optional)",
     "route": "subQ", "timing": "Evening fasted",
     "reason": "GH axis / recovery", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "10 mg blend + 3 mL BAC → 18 U; 8–12 wk cycle"},
    {"name": "BPC-157 + TB-500", "category": "peptide",
     "dose": 800, "unit": "mcg", "frequency": "daily PM",
     "route": "subQ", "timing": "Evening",
     "reason": "Tissue repair / recovery", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 90,
     "notes": "20 mg total + 2 mL BAC → 6–10 U range; 8–12 wk"},
    {"name": "DSIP", "category": "peptide",
     "dose": 300, "unit": "mcg", "frequency": "nightly (within cycle)",
     "route": "subQ", "timing": "Bedtime",
     "reason": "Deep sleep quality", "prescriber": "self",
     "cycle_status": "active", "adherence_pct": 85,
     "notes": "9 U at bedtime; 4–8 wk on / 2–4 wk off"},
]

proto_rows = []
for p in PROTOCOL:
    proto_rows.append({
        "start_date": PROTOCOL_START, "end_date": "",
        "category": p["category"], "name": p["name"],
        "dose": p["dose"], "unit": p["unit"], "frequency": p["frequency"],
        "route": p["route"], "timing": p["timing"], "reason": p["reason"],
        "prescriber": p["prescriber"], "cycle_status": p["cycle_status"],
        "adherence_pct": p["adherence_pct"], "notes": p["notes"],
    })

proto_df = pd.DataFrame(proto_rows)
proto_df.to_csv(DATA_DIR / "protocol.csv", index=False)
print(f"  wrote {len(proto_df)} rows to protocol.csv")
print(f"  by category: {proto_df['category'].value_counts().to_dict()}")

# ────────────────────────────────────────────────────────────────────────────
# Step 5: Apple Health GPX routes → training.csv
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 5: Write training.csv (from GPX routes)")
print("=" * 70)

NS = {"gpx": "http://www.topografix.com/GPX/1/1"}
gpx_files = sorted({p.stem.rstrip("-1"): p for p in WS.glob("route_*.gpx")}.values(),
                   key=lambda x: x.name)
# Dedupe — keep the file WITHOUT the trailing "-1"
seen = {}
for p in sorted(WS.glob("route_*.gpx")):
    key = p.stem.replace("-1", "")
    # Prefer file without -1 if both exist
    if key not in seen or "-1" not in p.stem:
        seen[key] = p
gpx_files = sorted(seen.values(), key=lambda x: x.name)

def parse_gpx(path: Path) -> dict | None:
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        pts = root.findall(".//gpx:trkpt", NS)
        if not pts:
            return None
        times = []
        coords = []
        eles = []
        for pt in pts:
            t = pt.find("gpx:time", NS)
            e = pt.find("gpx:ele", NS)
            if t is None:
                continue
            times.append(datetime.fromisoformat(t.text.replace("Z", "+00:00")))
            coords.append((float(pt.attrib["lat"]), float(pt.attrib["lon"])))
            if e is not None:
                eles.append(float(e.text))
        if not times:
            return None

        # Duration (Apple Health sometimes collapses timestamps to a single value
        # — in that case duration is unrecoverable from GPX alone)
        duration_min = (times[-1] - times[0]).total_seconds() / 60.0
        duration_recoverable = duration_min > 0.5
        # Distance via haversine
        from math import radians, sin, cos, sqrt, atan2
        def haversine(p1, p2):
            R = 6371000.0  # m
            lat1, lon1 = map(radians, p1)
            lat2, lon2 = map(radians, p2)
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            return 2 * R * atan2(sqrt(a), sqrt(1-a))
        dist_m = sum(haversine(coords[i-1], coords[i]) for i in range(1, len(coords)))
        dist_miles = dist_m / 1609.344
        # Elevation gain (sum of positive deltas)
        elev_gain_m = 0.0
        if eles:
            for i in range(1, len(eles)):
                d = eles[i] - eles[i-1]
                if d > 0:
                    elev_gain_m += d
        elev_gain_ft = elev_gain_m * 3.28084

        # Activity classification — Colorado mountain biker default; refine by
        # speed when duration is recoverable.
        if duration_recoverable:
            avg_speed_mph = dist_miles / (duration_min / 60.0)
            if avg_speed_mph < 5.0:
                activity, speed_note = "walk", f"avg speed {avg_speed_mph:.1f} mph"
            elif avg_speed_mph < 10:
                activity, speed_note = "ride", f"avg speed {avg_speed_mph:.1f} mph"
            else:
                activity, speed_note = "ride", f"avg speed {avg_speed_mph:.1f} mph"
        else:
            # No duration — longer routes default to ride for a MTB rider
            activity = "ride" if dist_miles >= 3.0 else "walk"
            speed_note = "duration unavailable in GPX"

        return {
            "date": times[0].strftime("%Y-%m-%d"),
            "activity_type": activity,
            "source": "apple_health_gpx",
            "duration_min": round(duration_min, 1) if duration_recoverable else "",
            "distance_miles": round(dist_miles, 2),
            "elevation_ft": int(round(elev_gain_ft)),
            "avg_hr_bpm": "",
            "max_hr_bpm": "",
            "avg_power_watts": "",
            "avg_cadence_rpm": "",
            "calories": "",
            "tss": "",
            "zone2_min": "",
            "notes": f"{speed_note} · {len(times)} GPS points",
        }
    except Exception as e:
        print(f"  ! failed parsing {path.name}: {e}")
        return None

training_rows = []
for gpx in gpx_files:
    row = parse_gpx(gpx)
    if row:
        training_rows.append(row)
        print(f"  parsed {gpx.name} → {row['date']} {row['activity_type']} "
              f"{row['distance_miles']} mi / {row['elevation_ft']} ft / {row['duration_min']} min")

training_df = pd.DataFrame(training_rows).sort_values("date").reset_index(drop=True)
training_df.to_csv(DATA_DIR / "training.csv", index=False)
print(f"  wrote {len(training_df)} rows to training.csv")

# ────────────────────────────────────────────────────────────────────────────
# Step 6: ECG → context_notes.csv
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 6: Write context_notes.csv (from ECG headers)")
print("=" * 70)

note_rows = []
for ecg in sorted(WS.glob("ecg_*.csv")):
    # Skip the -1 duplicates
    if ecg.stem.endswith("-1"):
        continue
    meta = {}
    with open(ecg, encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[0].strip():
                continue
            if row[0] == "Lead":
                break
            if len(row) >= 2:
                meta[row[0].strip()] = row[1].strip()
    rec = meta.get("Recorded Date", "")
    classification = meta.get("Classification", "Unknown")
    device = meta.get("Device", "Apple Watch")
    sym = meta.get("Symptoms", "") or "none"
    try:
        date_str = rec.split(" ")[0]
        # Validate
        datetime.fromisoformat(date_str)
    except Exception:
        date_str = ecg.stem.replace("ecg_", "")[:10]
    note_rows.append({
        "date": date_str,
        "category": "ecg",
        "note": f"Apple Watch ECG ({device}): Classification = {classification}; "
                f"symptoms = {sym}; sample rate ≈ {meta.get('Sample Rate', '?')}",
    })
    print(f"  parsed {ecg.name} → {date_str} · {classification}")

# Migration provenance note
note_rows.append({
    "date": TODAY,
    "category": "data_migration",
    "note": "v1.5 dummy data replaced with real personal data: LabCorp panel "
            "2025-09-30 + 2025-06-20, 19 InBody scans, full v3 protocol, "
            "Apple Health GPX routes (6) + ECG (4). Apple Health export.zip "
            "still needed for sleep/HR/HRV/steps → wearables.csv.",
})

notes_df = pd.DataFrame(note_rows).sort_values("date").reset_index(drop=True)
notes_df.to_csv(DATA_DIR / "context_notes.csv", index=False)
print(f"  wrote {len(notes_df)} rows to context_notes.csv")

# ────────────────────────────────────────────────────────────────────────────
# Step 7: Clear other dummy-only files (keep schema row only, no demo data)
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 7: Clear remaining dummy files (keep headers)")
print("=" * 70)

def reset_to_header(name: str):
    path = DATA_DIR / name
    if not path.exists():
        return
    with path.open() as f:
        header = f.readline().rstrip("\n")
    path.write_text(header + "\n")
    print(f"  cleared {name} (kept header only)")

for n in ["cgm_readings.csv", "ketone_readings.csv", "daily_log.csv",
          "action_items.csv", "wearables.csv"]:
    reset_to_header(n)

# ────────────────────────────────────────────────────────────────────────────
# Step 8: Append migration row to import_log.csv
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("STEP 8: Append to import_log.csv")
print("=" * 70)

import_log_path = DATA_DIR / "import_log.csv"
with open(import_log_path, "a", newline="") as f:
    w = csv.writer(f)
    ts = pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%S")
    w.writerow([ts, "bloodwork_pdf", "Ryan-Bloodtest.pdf",
                len(bw_df), 0, "", "migrate_real_data.py"])
    w.writerow([ts, "inbody_csv", "InBody-20260526.csv",
                len(inbody_df), 0, "", "migrate_real_data.py"])
    w.writerow([ts, "protocol_md", "weekly_peptide_supplement_protocol_v3.md",
                len(proto_df), 0, "", "migrate_real_data.py"])
    w.writerow([ts, "apple_health_gpx", "route_*.gpx (6 files)",
                len(training_df), 0, "", "migrate_real_data.py"])
    w.writerow([ts, "apple_health_ecg", "ecg_*.csv (4 files)",
                4, 0, "", "migrate_real_data.py"])
print(f"  appended 5 audit rows")

# ────────────────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("MIGRATION COMPLETE")
print("=" * 70)
print(f"  bloodwork.csv:     {len(bw_df)} rows ({bw_df['biomarker_canonical'].nunique()} unique markers × 2 draws)")
print(f"  inbody.csv:        {len(inbody_df)} rows")
print(f"  protocol.csv:      {len(proto_df)} compounds")
print(f"  training.csv:      {len(training_df)} rides from GPX")
print(f"  context_notes.csv: {len(notes_df)} entries (ECG + migration note)")
print(f"  cleared (empty for now): cgm, ketones, daily_log, action_items, wearables")
print(f"  *.demo.csv backups created for all replaced files")
