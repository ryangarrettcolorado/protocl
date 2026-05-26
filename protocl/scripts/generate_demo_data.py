"""Generate realistic seeded demo data for Protocōl.

Run once: python scripts/generate_demo_data.py
Output: populates data/ryan/*.csv and data/ryan/nof1_experiments.json

All rows are marked `source=demo` (or category="demo" where applicable) so
they can be filtered out later. Values trend realistically over the simulated
year and respect inter-marker physiology (e.g., TRT elevates HCT, Zone 2
training improves resting HR, etc.).
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


random.seed(42)
np.random.seed(42)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ryan"
DATA.mkdir(parents=True, exist_ok=True)

TODAY = datetime(2026, 5, 25)
START = TODAY - timedelta(days=365)


# ────────────────────────────────────────────────────────────────────────────
# Bloodwork — 4 quarterly draws, showing optimization trajectory
# ────────────────────────────────────────────────────────────────────────────

DRAW_DATES = [
    TODAY - timedelta(days=365),  # ~12 months ago, baseline
    TODAY - timedelta(days=270),  # ~9 months
    TODAY - timedelta(days=180),  # ~6 months
    TODAY - timedelta(days=90),   # ~3 months, current
]

# Each row: (canonical, panel, unit, lab_low, lab_high, [q1,q2,q3,q4 values])
BLOODWORK_DATA = [
    # Lipids — improving with diet + exercise
    ("total_cholesterol_mg_dl", "lipids", "mg/dL",  125,  200, [212, 198, 185, 178]),
    ("ldl_c_mg_dl",             "lipids", "mg/dL",    0,  100, [122, 108,  95,  82]),
    ("hdl_c_mg_dl",             "lipids", "mg/dL",   40,  100, [ 52,  58,  62,  68]),
    ("triglycerides_mg_dl",     "lipids", "mg/dL",    0,  150, [148, 112,  88,  72]),
    ("apob_mg_dl",              "lipids", "mg/dL",   40,  125, [ 98,  88,  78,  68]),
    ("lp_a_nmol_l",             "lipids", "nmol/L",   0,   75, [ 42,  44,  43,  42]),

    # Liver
    ("alt_u_l",                 "liver",  "U/L",      0,   55, [ 28,  24,  22,  20]),
    ("ast_u_l",                 "liver",  "U/L",      0,   48, [ 26,  24,  22,  21]),
    ("alp_u_l",                 "liver",  "U/L",     40,  129, [ 72,  68,  65,  62]),
    ("ggt_u_l",                 "liver",  "U/L",      0,   55, [ 32,  24,  20,  18]),
    ("albumin_g_dl",            "liver",  "g/dL",   3.5,  5.0, [4.3, 4.4, 4.5, 4.6]),

    # Kidney
    ("creatinine_mg_dl",        "kidney", "mg/dL",  0.7,  1.3, [1.05, 1.02, 1.00, 0.98]),
    ("bun_mg_dl",               "kidney", "mg/dL",    6,   24, [ 16,  15,  14,  13]),
    ("egfr_ml_min",             "kidney", "mL/min",  60,  200, [ 92,  95,  98, 101]),
    ("uric_acid_mg_dl",         "kidney", "mg/dL",  3.5,  7.2, [6.1, 5.8, 5.4, 5.0]),

    # Hormones — TRT optimized
    ("testosterone_total_ng_dl","hormones","ng/dL", 264,  916, [385, 720, 880, 950]),
    ("testosterone_free_pg_ml", "hormones","pg/mL", 8.7, 25.1, [ 9.8, 18.2, 22.5, 24.8]),
    ("shbg_nmol_l",             "hormones","nmol/L",  10,   57, [ 42,  35,  30,  27]),
    ("estradiol_pg_ml",         "hormones","pg/mL",   7,   42, [ 22,  32,  29,  28]),
    ("dhea_s_ug_dl",            "hormones","ug/dL",  71,  375, [220, 280, 340, 380]),
    ("cortisol_am_ug_dl",       "hormones","ug/dL", 6.2, 19.4, [16.8, 14.2, 12.8, 12.0]),
    ("igf_1_ng_ml",             "hormones","ng/mL",  88,  246, [165, 172, 178, 182]),

    # Thyroid
    ("tsh_uiu_ml",              "thyroid","uIU/mL", 0.45, 4.5, [2.4, 2.1, 1.8, 1.6]),
    ("free_t4_ng_dl",           "thyroid","ng/dL", 0.82,1.77, [1.18,1.22,1.28,1.32]),
    ("free_t3_pg_ml",           "thyroid","pg/mL", 2.0, 4.4,  [3.0, 3.2, 3.4, 3.6]),

    # Glucose / Insulin
    ("glucose_mg_dl",           "glucose_insulin","mg/dL", 70,  99, [ 96,  92,  88,  84]),
    ("hba1c_pct",               "glucose_insulin","%",    4.0, 5.6, [5.4, 5.2, 5.0, 4.9]),
    ("fasting_insulin_uiu_ml",  "glucose_insulin","uIU/mL", 2,  25, [ 11,   8,   6,   4]),
    ("homa_ir",                 "glucose_insulin","ratio",0.5, 2.0, [2.6, 1.8, 1.3, 0.83]),

    # Hematology — note HCT rises with TRT
    ("wbc_k_ul",                "hematology","K/uL",   3.4, 10.8, [5.8, 5.5, 5.2, 5.0]),
    ("rbc_m_ul",                "hematology","M/uL",  4.14, 5.80, [4.9, 5.0, 5.1, 5.2]),
    ("hemoglobin_g_dl",         "hematology","g/dL",  13.0, 17.7, [15.2,15.5,15.8,16.1]),
    ("hematocrit_pct",          "hematology","%",     38.5, 52.0, [44.5,46.0,47.5,49.0]),
    ("mcv_fl",                  "hematology","fL",      79,   97, [ 89,  90,  90,  91]),
    ("rdw_pct",                 "hematology","%",     11.5, 14.5, [12.6,12.5,12.4,12.3]),
    ("platelets_k_ul",          "hematology","K/uL",   150,  450, [245, 252, 248, 240]),
    ("lymphocytes_pct",         "hematology","%",       14,   46, [ 28,  30,  32,  33]),
    ("ferritin_ng_ml",          "hematology","ng/mL",   30,  400, [ 95, 102,  88,  74]),

    # Inflammation — coming down nicely
    ("hscrp_mg_l",              "inflammation","mg/L",   0,  3.0, [1.8, 1.2, 0.9, 0.6]),
    ("homocysteine_umol_l",     "inflammation","umol/L", 0,   15, [9.4, 8.6, 7.8, 7.2]),

    # Vitamins
    ("vitamin_d_ng_ml",         "vitamins_minerals","ng/mL",30,100, [ 38,  52,  65,  72]),
    ("vitamin_b12_pg_ml",       "vitamins_minerals","pg/mL",200,1100,[520, 640, 720, 780]),
    ("folate_ng_ml",            "vitamins_minerals","ng/mL", 3.0,20.0,[ 9.2,12.4,14.8,15.5]),
    ("magnesium_rbc_mg_dl",     "vitamins_minerals","mg/dL",4.2,6.8, [5.4, 5.8, 6.1, 6.3]),

    # Cardiovascular
    ("omega_3_index_pct",       "cardiovascular","%",      4,  12, [4.8, 6.4, 7.8, 8.9]),
]

rows = []
for canonical, panel, unit, lab_lo, lab_hi, values in BLOODWORK_DATA:
    for date, value in zip(DRAW_DATES, values):
        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "panel": panel,
            "biomarker_canonical": canonical,
            "value": value,
            "unit": unit,
            "lab_ref_low": lab_lo,
            "lab_ref_high": lab_hi,
            "source_lab": "demo",
            "notes": "",
        })
pd.DataFrame(rows).to_csv(DATA / "bloodwork.csv", index=False)
print(f"bloodwork.csv: {len(rows)} rows across {len(DRAW_DATES)} draws")


# ────────────────────────────────────────────────────────────────────────────
# Protocol — 8-10 active items + 3 historical changes
# ────────────────────────────────────────────────────────────────────────────

protocol_rows = [
    # Active hormones
    {"start_date": "2025-08-01", "end_date": "", "category": "hormone",
     "name": "Testosterone Cypionate", "dose": "160", "unit": "mg",
     "frequency": "weekly (split E3.5D)", "route": "subq injection",
     "timing": "Mon/Thu AM", "reason": "TRT — restore physiologic levels",
     "prescriber": "Defy Medical", "cycle_status": "active",
     "adherence_pct": 100, "notes": "0.16 mL × 2 per week"},
    {"start_date": "2025-09-15", "end_date": "", "category": "hormone",
     "name": "Anastrozole", "dose": "0.25", "unit": "mg",
     "frequency": "as needed (E2 control)", "route": "oral",
     "timing": "with TRT dose", "reason": "Manage estradiol on TRT",
     "prescriber": "Defy Medical", "cycle_status": "active",
     "adherence_pct": 80, "notes": "Only when E2 > 35"},

    # Peptide cycle
    {"start_date": "2026-02-01", "end_date": "", "category": "peptide",
     "name": "BPC-157", "dose": "250", "unit": "mcg",
     "frequency": "daily", "route": "subq injection",
     "timing": "AM, near injury site", "reason": "Connective tissue repair (shoulder)",
     "prescriber": "compounding pharmacy", "cycle_status": "active",
     "adherence_pct": 95, "notes": "8-week cycle"},
    {"start_date": "2026-03-10", "end_date": "", "category": "peptide",
     "name": "CJC-1295 / Ipamorelin", "dose": "300/300", "unit": "mcg",
     "frequency": "5 nights/week", "route": "subq injection",
     "timing": "bedtime, fasted", "reason": "GH pulse support, body comp, sleep",
     "prescriber": "compounding pharmacy", "cycle_status": "active",
     "adherence_pct": 90, "notes": "5-on, 2-off"},

    # Core supplements
    {"start_date": "2025-06-01", "end_date": "", "category": "supplement",
     "name": "Creatine Monohydrate", "dose": "5", "unit": "g",
     "frequency": "daily", "route": "oral",
     "timing": "any time", "reason": "Strength, cognitive support, longevity",
     "prescriber": "self", "cycle_status": "active",
     "adherence_pct": 98, "notes": ""},
    {"start_date": "2025-06-01", "end_date": "", "category": "supplement",
     "name": "Omega-3 (EPA/DHA)", "dose": "3", "unit": "g",
     "frequency": "daily", "route": "oral",
     "timing": "with meals", "reason": "CV health, omega-3 index target",
     "prescriber": "self", "cycle_status": "active",
     "adherence_pct": 95, "notes": "Nordic Naturals Ultimate Omega"},
    {"start_date": "2025-06-01", "end_date": "", "category": "supplement",
     "name": "Vitamin D3 + K2", "dose": "5000/200", "unit": "IU/mcg",
     "frequency": "daily", "route": "oral",
     "timing": "with breakfast (fat)", "reason": "Vit D target 60-80",
     "prescriber": "self", "cycle_status": "active",
     "adherence_pct": 95, "notes": ""},
    {"start_date": "2025-06-01", "end_date": "", "category": "supplement",
     "name": "Magnesium Glycinate", "dose": "400", "unit": "mg",
     "frequency": "daily", "route": "oral",
     "timing": "bedtime", "reason": "RBC Mg target, sleep quality",
     "prescriber": "self", "cycle_status": "active",
     "adherence_pct": 95, "notes": ""},
    {"start_date": "2025-09-01", "end_date": "", "category": "supplement",
     "name": "Berberine", "dose": "500", "unit": "mg",
     "frequency": "2x daily with carb meals", "route": "oral",
     "timing": "lunch + dinner", "reason": "Glucose / insulin sensitivity",
     "prescriber": "self", "cycle_status": "active",
     "adherence_pct": 85, "notes": ""},
    {"start_date": "2025-10-01", "end_date": "", "category": "supplement",
     "name": "Rapamycin", "dose": "6", "unit": "mg",
     "frequency": "weekly", "route": "oral",
     "timing": "Sunday AM fasted", "reason": "Longevity / mTOR cycling",
     "prescriber": "AgelessRx", "cycle_status": "active",
     "adherence_pct": 100, "notes": "8-week on / 4-week off pattern"},

    # Historical
    {"start_date": "2025-06-01", "end_date": "2025-09-30", "category": "supplement",
     "name": "Ashwagandha (KSM-66)", "dose": "600", "unit": "mg",
     "frequency": "daily", "route": "oral",
     "timing": "PM", "reason": "Cortisol control during high-stress period",
     "prescriber": "self", "cycle_status": "completed",
     "adherence_pct": 90, "notes": "Discontinued after cortisol normalized"},
    {"start_date": "2025-07-15", "end_date": "2025-12-15", "category": "peptide",
     "name": "Tesamorelin", "dose": "1", "unit": "mg",
     "frequency": "daily", "route": "subq injection",
     "timing": "AM fasted", "reason": "Visceral fat reduction trial",
     "prescriber": "compounding pharmacy", "cycle_status": "completed",
     "adherence_pct": 92, "notes": "5-month cycle complete"},
    {"start_date": "2025-08-01", "end_date": "2025-09-15", "category": "supplement",
     "name": "DIM", "dose": "200", "unit": "mg",
     "frequency": "daily", "route": "oral",
     "timing": "AM", "reason": "E2 management before anastrozole",
     "prescriber": "self", "cycle_status": "completed",
     "adherence_pct": 100, "notes": "Replaced by anastrozole"},
]
pd.DataFrame(protocol_rows).to_csv(DATA / "protocol.csv", index=False)
print(f"protocol.csv: {len(protocol_rows)} items")


# ────────────────────────────────────────────────────────────────────────────
# InBody — monthly, 12 months, gradual recomp
# ────────────────────────────────────────────────────────────────────────────

inbody_rows = []
weight_start, bf_start, lean_start = 195.0, 22.0, 152.1
for i in range(13):
    date = (START + timedelta(days=30 * i)).strftime("%Y-%m-%d")
    progress = i / 12.0
    # Body fat from 22% → 14%, lean mass +6 lbs
    weight = weight_start + np.random.normal(0, 0.6) - progress * 4
    bf_pct = bf_start - progress * 8 + np.random.normal(0, 0.3)
    lean = lean_start + progress * 6 + np.random.normal(0, 0.4)
    fat_mass = weight * bf_pct / 100
    smm = lean * 0.59  # skeletal muscle mass typically ~58-60% of lean
    inbody_rows.append({
        "date": date,
        "weight_lbs": round(weight, 1),
        "skeletal_muscle_mass_lbs": round(smm, 1),
        "body_fat_mass_lbs": round(fat_mass, 1),
        "body_fat_pct": round(bf_pct, 1),
        "visceral_fat_level": max(3, round(10 - progress * 5)),
        "lean_mass_lbs": round(lean, 1),
        "total_body_water_lbs": round(lean * 0.73, 1),
        "bmr_kcal": round(1700 + lean * 1.5),
        "source": "demo",
        "notes": "",
    })
pd.DataFrame(inbody_rows).to_csv(DATA / "inbody.csv", index=False)
print(f"inbody.csv: {len(inbody_rows)} scans")


# ────────────────────────────────────────────────────────────────────────────
# Training — 16 weeks of activities (road cycling primary)
# ────────────────────────────────────────────────────────────────────────────

training_rows = []
max_hr = 220 - 42  # 178
z2_low, z2_high = int(max_hr * 0.60), int(max_hr * 0.70)
for week in range(16):
    week_start = TODAY - timedelta(days=(16 - week) * 7)
    # 4-5 sessions per week
    sessions = [
        ("ride", 90, 22, 1500, 145, "Tuesday"),
        ("ride", 120, 30, 2200, 138, "Thursday"),
        ("mountain_bike", 75, 12, 1800, 152, "Saturday"),
        ("ride", 180, 45, 2800, 142, "Sunday"),
        ("strength", 50, 0, 0, 118, "Wednesday"),
    ]
    for i, (act, dur, dist, elev, hr, dow) in enumerate(sessions):
        d = week_start + timedelta(days=i)
        if d > TODAY:
            continue
        # Slight variability
        dur_v = dur + np.random.randint(-8, 9)
        hr_v = hr + np.random.randint(-5, 6)
        zone2 = dur_v if z2_low <= hr_v <= z2_high else max(0, int(dur_v * 0.35))
        training_rows.append({
            "date": d.strftime("%Y-%m-%d"),
            "activity_type": act,
            "source": "demo",
            "duration_min": dur_v,
            "distance_miles": dist + (np.random.random() - 0.5) * 2 if dist else 0,
            "elevation_ft": elev + np.random.randint(-100, 100) if elev else 0,
            "avg_hr_bpm": hr_v,
            "max_hr_bpm": hr_v + np.random.randint(10, 25),
            "avg_power_watts": 195 + np.random.randint(-15, 16) if act in ("ride", "mountain_bike") else 0,
            "avg_cadence_rpm": 86 + np.random.randint(-5, 6) if act in ("ride", "mountain_bike") else 0,
            "calories": int(dur_v * 11) if act != "strength" else int(dur_v * 6),
            "tss": int(dur_v * 1.2) if act != "strength" else 0,
            "zone2_min": zone2 if act != "strength" else 0,
            "notes": "",
        })
pd.DataFrame(training_rows).to_csv(DATA / "training.csv", index=False)
print(f"training.csv: {len(training_rows)} sessions")


# ────────────────────────────────────────────────────────────────────────────
# Wearables — 90 days daily
# ────────────────────────────────────────────────────────────────────────────

wear_rows = []
for i in range(90):
    d = TODAY - timedelta(days=89 - i)
    # Resting HR trending down 56 → 52 over 90 days
    rhr = 56 - i * 0.04 + np.random.normal(0, 1.5)
    hrv = 58 + i * 0.10 + np.random.normal(0, 6)
    sleep = 7.4 + np.random.normal(0, 0.6)
    deep = sleep * 0.18 + np.random.normal(0, 0.1)
    rem = sleep * 0.22 + np.random.normal(0, 0.1)
    wear_rows.append({
        "date": d.strftime("%Y-%m-%d"),
        "resting_hr_bpm": round(rhr, 1),
        "hrv_sdnn_ms": round(max(20, hrv), 1),
        "vo2_max_ml_kg_min": round(46.5 + i * 0.015 + np.random.normal(0, 0.4), 1),
        "sleep_duration_hrs": round(max(5.0, sleep), 2),
        "sleep_deep_hrs": round(max(0.5, deep), 2),
        "sleep_rem_hrs": round(max(0.5, rem), 2),
        "sleep_consistency_pct": int(78 + np.random.randint(-12, 13)),
        "respiratory_rate_brpm": round(14.5 + np.random.normal(0, 0.6), 1),
        "spo2_pct": round(97 + np.random.normal(0, 0.8), 1),
        "active_calories": int(550 + np.random.randint(-180, 280)),
        "steps": int(9500 + np.random.randint(-2800, 4500)),
        "stand_hrs": int(11 + np.random.randint(-3, 3)),
        "skin_temp_delta_f": round(np.random.normal(0, 0.4), 2),
        "source": "demo",
    })
pd.DataFrame(wear_rows).to_csv(DATA / "wearables.csv", index=False)
print(f"wearables.csv: {len(wear_rows)} days")


# ────────────────────────────────────────────────────────────────────────────
# CGM — 30 days, 5-min intervals, TIR ~82%
# ────────────────────────────────────────────────────────────────────────────

cgm_rows = []
for day in range(30):
    base = TODAY - timedelta(days=29 - day)
    # 5-minute intervals = 288 readings per day
    for m in range(0, 24 * 60, 5):
        ts = base.replace(hour=0, minute=0, second=0) + timedelta(minutes=m)
        # Diurnal pattern + meal spikes at 8, 13, 19h
        hour = m / 60.0
        glucose = 88
        # Meal spikes
        for meal_h, peak in [(8, 28), (13, 32), (19, 25)]:
            elapsed = hour - meal_h
            if 0 <= elapsed <= 2.5:
                # Bell-shaped postprandial response
                glucose += peak * math.exp(-((elapsed - 0.75) ** 2) / 0.5)
        # Dawn phenomenon
        if 4 <= hour <= 7:
            glucose += 6
        # Overnight low
        if 2 <= hour <= 4:
            glucose -= 4
        glucose += np.random.normal(0, 3.5)
        glucose = max(60, min(195, glucose))
        cgm_rows.append({
            "datetime": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "glucose_mg_dl": round(glucose, 1),
            "glucose_mmol_l": round(glucose / 18.0, 2),
            "source": "demo",
            "sensor_type": "cgm",
            "notes": "",
        })
pd.DataFrame(cgm_rows).to_csv(DATA / "cgm_readings.csv", index=False)
print(f"cgm_readings.csv: {len(cgm_rows)} readings ({len(cgm_rows)//288} days)")


# ────────────────────────────────────────────────────────────────────────────
# Ketones — 14 days GK+ readings
# ────────────────────────────────────────────────────────────────────────────

ket_rows = []
for day in range(14):
    d = TODAY - timedelta(days=13 - day)
    for hr in [6, 14]:
        ts = d.replace(hour=hr, minute=0, second=0)
        ketones = round(0.3 + np.random.uniform(0, 1.5), 2)
        glucose = round(82 + np.random.normal(0, 6), 1)
        gki = round((glucose / 18.0) / max(0.1, ketones), 2)
        ket_rows.append({
            "datetime": ts.strftime("%Y-%m-%dT%H:%M:%S"),
            "blood_ketones_mmol_l": ketones,
            "blood_glucose_mg_dl": glucose,
            "gki": gki,
            "source": "demo",
            "notes": "",
        })
pd.DataFrame(ket_rows).to_csv(DATA / "ketone_readings.csv", index=False)
print(f"ketone_readings.csv: {len(ket_rows)} readings")


# ────────────────────────────────────────────────────────────────────────────
# Daily log — 60 days
# ────────────────────────────────────────────────────────────────────────────

daily_rows = []
for i in range(60):
    d = TODAY - timedelta(days=59 - i)
    protein = int(170 + np.random.randint(-20, 30))
    carbs = int(200 + np.random.randint(-60, 90))
    fat = int(85 + np.random.randint(-15, 20))
    daily_rows.append({
        "date": d.strftime("%Y-%m-%d"),
        "calories_kcal": protein * 4 + carbs * 4 + fat * 9,
        "protein_g": protein,
        "carbs_g": carbs,
        "fat_g": fat,
        "fiber_g": int(32 + np.random.randint(-8, 12)),
        "water_oz": int(96 + np.random.randint(-20, 25)),
        "sleep_hrs": round(7.4 + np.random.normal(0, 0.5), 1),
        "sleep_quality_1_10": int(7 + np.random.randint(-2, 3)),
        "notes": "",
    })
pd.DataFrame(daily_rows).to_csv(DATA / "daily_log.csv", index=False)
print(f"daily_log.csv: {len(daily_rows)} days")


# ────────────────────────────────────────────────────────────────────────────
# Action items — 5 open
# ────────────────────────────────────────────────────────────────────────────

action_rows = [
    {"id": "act_001", "title": "Recheck hematocrit (TRT polycythemia watch)",
     "priority": "high", "category": "testing",
     "why_it_matters": "Hematocrit trending up — 44.5 → 49.0 over 12 months. Above 52% = donate blood.",
     "due_date": (TODAY + timedelta(days=21)).strftime("%Y-%m-%d"),
     "related_metrics": "hematocrit_pct,hemoglobin_g_dl",
     "status": "open", "source": "auto_risk",
     "created_date": (TODAY - timedelta(days=14)).strftime("%Y-%m-%d")},
    {"id": "act_002", "title": "Increase weekly Zone 2 minutes to 150",
     "priority": "medium", "category": "training",
     "why_it_matters": "Currently averaging 110 min/week. 150+ correlates with mitochondrial gains.",
     "due_date": (TODAY + timedelta(days=14)).strftime("%Y-%m-%d"),
     "related_metrics": "zone2_min,vo2_max_ml_kg_min",
     "status": "in_progress", "source": "auto_recommendation",
     "created_date": (TODAY - timedelta(days=7)).strftime("%Y-%m-%d")},
    {"id": "act_003", "title": "Reorder Omega-3 — supply runs out next week",
     "priority": "medium", "category": "protocol",
     "why_it_matters": "Maintaining omega-3 index above 8% drove inflammation gains.",
     "due_date": (TODAY + timedelta(days=5)).strftime("%Y-%m-%d"),
     "related_metrics": "omega_3_index_pct,hscrp_mg_l",
     "status": "open", "source": "manual",
     "created_date": (TODAY - timedelta(days=2)).strftime("%Y-%m-%d")},
    {"id": "act_004", "title": "Schedule next quarterly bloodwork",
     "priority": "high", "category": "testing",
     "why_it_matters": "Last draw was 90 days ago. Quarterly cadence due.",
     "due_date": (TODAY + timedelta(days=10)).strftime("%Y-%m-%d"),
     "related_metrics": "",
     "status": "open", "source": "manual",
     "created_date": TODAY.strftime("%Y-%m-%d")},
    {"id": "act_005", "title": "Review ferritin downtrend (95 → 74)",
     "priority": "low", "category": "nutrition",
     "why_it_matters": "Ferritin gradually trending down; consider red meat frequency.",
     "due_date": (TODAY + timedelta(days=30)).strftime("%Y-%m-%d"),
     "related_metrics": "ferritin_ng_ml,iron_ug_dl",
     "status": "planned", "source": "auto_recommendation",
     "created_date": (TODAY - timedelta(days=10)).strftime("%Y-%m-%d")},
]
pd.DataFrame(action_rows).to_csv(DATA / "action_items.csv", index=False)
print(f"action_items.csv: {len(action_rows)} items")


# ────────────────────────────────────────────────────────────────────────────
# Context notes
# ────────────────────────────────────────────────────────────────────────────

context_rows = [
    {"date": (TODAY - timedelta(days=45)).strftime("%Y-%m-%d"), "category": "travel",
     "note": "5-day trip to Phoenix — disrupted sleep, glucose elevated"},
    {"date": (TODAY - timedelta(days=30)).strftime("%Y-%m-%d"), "category": "deload",
     "note": "Planned training deload week"},
    {"date": (TODAY - timedelta(days=12)).strftime("%Y-%m-%d"), "category": "illness",
     "note": "Mild cold, 3 days reduced training intensity"},
]
pd.DataFrame(context_rows).to_csv(DATA / "context_notes.csv", index=False)
print(f"context_notes.csv: {len(context_rows)} notes")


# ────────────────────────────────────────────────────────────────────────────
# Import log — empty initial
# ────────────────────────────────────────────────────────────────────────────

pd.DataFrame(columns=[
    "timestamp", "source_type", "filename", "rows_imported",
    "rows_skipped_duplicate", "errors", "imported_by"
]).to_csv(DATA / "import_log.csv", index=False)
print("import_log.csv: empty")


# ────────────────────────────────────────────────────────────────────────────
# N=1 experiments
# ────────────────────────────────────────────────────────────────────────────

nof1 = [
    {
        "id": "exp_001",
        "title": "Berberine 1000mg/day vs baseline — fasting glucose",
        "hypothesis": "If I take 500mg berberine 2x/day with carb meals, fasting glucose will drop by ≥5 mg/dL over 8 weeks.",
        "intervention": {
            "name": "Berberine",
            "type": "supplement",
            "dose": "500mg 2x daily",
            "frequency": "with lunch + dinner",
            "start_date": "2025-09-01",
            "end_date": "2025-10-27",
        },
        "washout_period_days": 14,
        "control_period": {"start_date": "2025-07-15", "end_date": "2025-08-28"},
        "primary_outcome": {
            "metric": "glucose_mg_dl (fasting)",
            "source": "bloodwork",
            "direction": "decrease",
            "minimum_effect_size": "5 mg/dL",
        },
        "secondary_outcomes": ["hba1c_pct", "homa_ir"],
        "confounders_to_control": ["sleep_hrs", "training_load", "stress_notes"],
        "blinding": "none",
        "crossover_periods": 1,
        "measurement_frequency": "on_draw",
        "status": "complete",
        "results": {
            "baseline_mean": 92.0,
            "intervention_mean": 84.0,
            "delta": -8.0,
            "delta_pct": -8.7,
            "cohens_d": 1.42,
            "verdict": "likely_beneficial",
            "confidence": "high",
            "notes": "Glucose dropped 8 mg/dL; HOMA-IR halved. Continuing protocol.",
        },
        "sources_informing_design": [
            {"name": "Yin et al. 2008 — Metformin vs Berberine RCT",
             "url": "https://pubmed.ncbi.nlm.nih.gov/18397984/", "tier": "T1"},
        ],
        "created_date": "2025-08-25",
        "last_updated": "2025-11-10",
    },
    {
        "id": "exp_002",
        "title": "Methylene Blue 10mg AM — cognitive + HRV response",
        "hypothesis": "If I take 10mg MB in the morning, subjective focus + HRV will improve over 4 weeks.",
        "intervention": {
            "name": "Methylene Blue (USP)",
            "type": "supplement",
            "dose": "10mg",
            "frequency": "daily AM",
            "start_date": "2026-01-05",
            "end_date": "2026-02-02",
        },
        "washout_period_days": 14,
        "control_period": {"start_date": "2025-11-20", "end_date": "2025-12-22"},
        "primary_outcome": {
            "metric": "hrv_sdnn_ms (7-day avg)",
            "source": "wearable",
            "direction": "increase",
            "minimum_effect_size": "5 ms",
        },
        "secondary_outcomes": ["subjective_focus_1_10"],
        "confounders_to_control": ["sleep_hrs", "caffeine_intake"],
        "blinding": "none",
        "crossover_periods": 1,
        "measurement_frequency": "daily",
        "status": "complete",
        "results": {
            "baseline_mean": 62.4,
            "intervention_mean": 64.1,
            "delta": 1.7,
            "delta_pct": 2.7,
            "cohens_d": 0.28,
            "verdict": "inconclusive",
            "confidence": "low",
            "notes": "Subjective focus mildly improved but HRV change within noise. Inconclusive — would need longer trial.",
        },
        "sources_informing_design": [
            {"name": "Tucker et al. 2018 — Mitochondrial effects of MB",
             "url": "https://pubmed.ncbi.nlm.nih.gov/29554500/", "tier": "T3"},
        ],
        "created_date": "2025-12-28",
        "last_updated": "2026-02-05",
    },
    {
        "id": "exp_003",
        "title": "CJC-1295/Ipamorelin nightly — body comp + sleep",
        "hypothesis": "If I run 300/300 mcg nightly for 12 weeks, lean mass will increase by ≥2 lbs and deep sleep by ≥10%.",
        "intervention": {
            "name": "CJC-1295 + Ipamorelin",
            "type": "peptide",
            "dose": "300mcg / 300mcg",
            "frequency": "5 nights/week bedtime fasted",
            "start_date": "2026-03-10",
            "end_date": "2026-06-02",
        },
        "washout_period_days": 21,
        "control_period": {"start_date": "2025-12-15", "end_date": "2026-02-17"},
        "primary_outcome": {
            "metric": "lean_mass_lbs",
            "source": "inbody",
            "direction": "increase",
            "minimum_effect_size": "2 lbs",
        },
        "secondary_outcomes": ["sleep_deep_hrs", "igf_1_ng_ml"],
        "confounders_to_control": ["protein_g", "training_load", "sleep_hrs"],
        "blinding": "none",
        "crossover_periods": 1,
        "measurement_frequency": "weekly",
        "status": "active",
        "results": {
            "baseline_mean": None,
            "intervention_mean": None,
            "delta": None,
            "delta_pct": None,
            "cohens_d": None,
            "verdict": "inconclusive",
            "confidence": "low",
            "notes": "In progress — 11/12 weeks complete.",
        },
        "sources_informing_design": [
            {"name": "Sigalos & Pastuszak 2018 — GHRP safety",
             "url": "https://pubmed.ncbi.nlm.nih.gov/29463274/", "tier": "T3"},
        ],
        "created_date": "2026-03-05",
        "last_updated": "2026-05-20",
    },
]
with (DATA / "nof1_experiments.json").open("w") as f:
    json.dump(nof1, f, indent=2)
print(f"nof1_experiments.json: {len(nof1)} experiments")


print("\n✅ Demo data generation complete.")
print(f"   Output: {DATA}")
