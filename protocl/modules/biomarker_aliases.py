"""Cross-lab biomarker name normalization.

Maps the many variants used by LabCorp, Quest, Empire City, etc. to a single
canonical key per biomarker. Canonical keys are snake_case with the unit
appended to disambiguate (e.g. testosterone_total_ng_dl).
"""
from __future__ import annotations


# Map of canonical_key -> list of common aliases (lowercased, stripped)
ALIASES: dict[str, list[str]] = {
    # Lipids
    "total_cholesterol_mg_dl": ["total cholesterol", "cholesterol total", "chol"],
    "ldl_c_mg_dl": ["ldl", "ldl-c", "ldl cholesterol", "ldl direct"],
    "hdl_c_mg_dl": ["hdl", "hdl-c", "hdl cholesterol"],
    "triglycerides_mg_dl": ["triglycerides", "trig", "tg"],
    "apob_mg_dl": ["apob", "apolipoprotein b", "apo b"],
    "lp_a_nmol_l": ["lp(a)", "lipoprotein(a)", "lpa"],
    "ldl_p_nmol_l": ["ldl-p", "ldl particle number"],

    # Liver
    "alt_u_l": ["alt", "alanine aminotransferase", "sgpt"],
    "ast_u_l": ["ast", "aspartate aminotransferase", "sgot"],
    "alp_u_l": ["alp", "alkaline phosphatase", "alk phos"],
    "ggt_u_l": ["ggt", "gamma-glutamyl transferase"],
    "albumin_g_dl": ["albumin"],
    "total_bilirubin_mg_dl": ["total bilirubin", "bilirubin total"],

    # Kidney
    "creatinine_mg_dl": ["creatinine", "creat"],
    "bun_mg_dl": ["bun", "blood urea nitrogen", "urea nitrogen"],
    "egfr_ml_min": ["egfr", "estimated gfr", "gfr"],
    "cystatin_c_mg_l": ["cystatin c"],
    "uric_acid_mg_dl": ["uric acid"],

    # Hormones
    "testosterone_total_ng_dl": ["total testosterone", "testosterone total", "test total"],
    "testosterone_free_pg_ml": ["free testosterone", "testosterone free"],
    "shbg_nmol_l": ["shbg", "sex hormone binding globulin"],
    "estradiol_pg_ml": ["estradiol", "e2", "estradiol sensitive"],
    "dhea_s_ug_dl": ["dhea-s", "dhea sulfate", "dheas"],
    "cortisol_am_ug_dl": ["cortisol am", "morning cortisol", "cortisol"],
    "progesterone_ng_ml": ["progesterone"],
    "lh_miu_ml": ["lh", "luteinizing hormone"],
    "fsh_miu_ml": ["fsh", "follicle stimulating hormone"],
    "prolactin_ng_ml": ["prolactin"],
    "igf_1_ng_ml": ["igf-1", "igf1", "insulin-like growth factor 1"],

    # Thyroid
    "tsh_uiu_ml": ["tsh", "thyroid stimulating hormone"],
    "free_t4_ng_dl": ["free t4", "ft4"],
    "free_t3_pg_ml": ["free t3", "ft3"],
    "reverse_t3_ng_dl": ["reverse t3", "rt3"],
    "tpo_ab_iu_ml": ["tpo antibodies", "thyroid peroxidase antibody"],

    # Glucose / Insulin
    "glucose_mg_dl": ["glucose", "fasting glucose"],
    "hba1c_pct": ["hba1c", "a1c", "hemoglobin a1c"],
    "fasting_insulin_uiu_ml": ["insulin", "fasting insulin"],
    "homa_ir": ["homa-ir", "homa ir"],
    "c_peptide_ng_ml": ["c-peptide", "c peptide"],

    # Hematology / CBC
    "wbc_k_ul": ["wbc", "white blood cells"],
    "rbc_m_ul": ["rbc", "red blood cells"],
    "hemoglobin_g_dl": ["hemoglobin", "hgb"],
    "hematocrit_pct": ["hematocrit", "hct"],
    "mcv_fl": ["mcv", "mean corpuscular volume"],
    "rdw_pct": ["rdw"],
    "platelets_k_ul": ["platelets", "plt"],
    "lymphocytes_pct": ["lymphocytes %", "lymphs %", "lymphocyte percent"],
    "neutrophils_pct": ["neutrophils %", "neuts %"],
    "ferritin_ng_ml": ["ferritin"],
    "iron_ug_dl": ["iron"],
    "tibc_ug_dl": ["tibc"],
    "transferrin_saturation_pct": ["transferrin saturation", "tsat"],

    # Inflammation
    "hscrp_mg_l": ["hs-crp", "hscrp", "c-reactive protein high sensitivity"],
    "homocysteine_umol_l": ["homocysteine"],
    "fibrinogen_mg_dl": ["fibrinogen"],

    # Vitamins / Minerals
    "vitamin_d_ng_ml": ["vitamin d", "25-oh vitamin d", "25(oh)d"],
    "vitamin_b12_pg_ml": ["b12", "vitamin b12"],
    "folate_ng_ml": ["folate", "rbc folate"],
    "magnesium_rbc_mg_dl": ["rbc magnesium", "magnesium rbc"],
    "zinc_ug_dl": ["zinc"],

    # Cardiovascular
    "lp_pla2_ng_ml": ["lp-pla2"],
    "omega_3_index_pct": ["omega-3 index"],
    "psa_ng_ml": ["psa", "prostate specific ag", "prostate specific antigen", "prostate-specific ag"],

    # Lipids (extended)
    "vldl_c_mg_dl": ["vldl", "vldl cholesterol", "vldl cholesterol cal"],

    # CBC (extended)
    "mch_pg": ["mch", "mean corpuscular hemoglobin"],
    "mchc_g_dl": ["mchc"],
    "neutrophils_abs_k_ul": ["neutrophils (absolute)", "neuts abs"],
    "lymphocytes_abs_k_ul": ["lymphs (absolute)", "lymphocytes absolute"],
    "monocytes_pct": ["monocytes", "monocytes %"],
    "eosinophils_pct": ["eos", "eos %", "eosinophils"],
    "basophils_pct": ["basos", "basos %", "basophils"],

    # CMP (extended)
    "sodium_mmol_l": ["sodium"],
    "potassium_mmol_l": ["potassium"],
    "chloride_mmol_l": ["chloride"],
    "co2_mmol_l": ["co2", "carbon dioxide", "carbon dioxide, total", "carbon dioxide total"],
    "calcium_mg_dl": ["calcium"],
    "total_protein_g_dl": ["total protein", "protein total", "protein, total"],
    "globulin_g_dl": ["globulin", "globulin total", "globulin, total"],
    "bun_creatinine_ratio": ["bun/creatinine ratio", "bun creatinine ratio"],
}


_REVERSE: dict[str, str] = {}
for canonical, alts in ALIASES.items():
    _REVERSE[canonical.lower()] = canonical
    for alt in alts:
        _REVERSE[alt.lower().strip()] = canonical


def canonicalize(name: str) -> str | None:
    """Return the canonical key for a free-text biomarker name, or None."""
    if not name:
        return None
    return _REVERSE.get(name.lower().strip())


def display_name(canonical: str) -> str:
    """Human-friendly display name for a canonical key."""
    return DISPLAY.get(canonical, canonical.replace("_", " ").title())


# Pretty display names overriding the snake_case default
DISPLAY: dict[str, str] = {
    "total_cholesterol_mg_dl":   "Total Cholesterol",
    "ldl_c_mg_dl":               "LDL-C",
    "hdl_c_mg_dl":               "HDL-C",
    "triglycerides_mg_dl":       "Triglycerides",
    "apob_mg_dl":                "ApoB",
    "lp_a_nmol_l":               "Lp(a)",
    "ldl_p_nmol_l":              "LDL-P",
    "alt_u_l":                   "ALT",
    "ast_u_l":                   "AST",
    "alp_u_l":                   "ALP",
    "ggt_u_l":                   "GGT",
    "albumin_g_dl":              "Albumin",
    "total_bilirubin_mg_dl":     "Total Bilirubin",
    "creatinine_mg_dl":          "Creatinine",
    "bun_mg_dl":                 "BUN",
    "egfr_ml_min":               "eGFR",
    "cystatin_c_mg_l":           "Cystatin C",
    "uric_acid_mg_dl":           "Uric Acid",
    "testosterone_total_ng_dl":  "Total Testosterone",
    "testosterone_free_pg_ml":   "Free Testosterone",
    "shbg_nmol_l":               "SHBG",
    "estradiol_pg_ml":            "Estradiol (E2)",
    "dhea_s_ug_dl":              "DHEA-S",
    "cortisol_am_ug_dl":         "Cortisol (AM)",
    "progesterone_ng_ml":        "Progesterone",
    "lh_miu_ml":                 "LH",
    "fsh_miu_ml":                "FSH",
    "prolactin_ng_ml":           "Prolactin",
    "igf_1_ng_ml":               "IGF-1",
    "tsh_uiu_ml":                "TSH",
    "free_t4_ng_dl":             "Free T4",
    "free_t3_pg_ml":             "Free T3",
    "reverse_t3_ng_dl":          "Reverse T3",
    "tpo_ab_iu_ml":              "TPO Antibodies",
    "glucose_mg_dl":             "Fasting Glucose",
    "hba1c_pct":                 "HbA1c",
    "fasting_insulin_uiu_ml":    "Fasting Insulin",
    "homa_ir":                   "HOMA-IR",
    "c_peptide_ng_ml":           "C-Peptide",
    "wbc_k_ul":                  "WBC",
    "rbc_m_ul":                  "RBC",
    "hemoglobin_g_dl":           "Hemoglobin",
    "hematocrit_pct":            "Hematocrit",
    "mcv_fl":                    "MCV",
    "rdw_pct":                   "RDW",
    "platelets_k_ul":            "Platelets",
    "lymphocytes_pct":           "Lymphocytes %",
    "neutrophils_pct":           "Neutrophils %",
    "ferritin_ng_ml":            "Ferritin",
    "iron_ug_dl":                "Iron",
    "tibc_ug_dl":                "TIBC",
    "transferrin_saturation_pct":"Transferrin Saturation",
    "hscrp_mg_l":                "hs-CRP",
    "homocysteine_umol_l":       "Homocysteine",
    "fibrinogen_mg_dl":          "Fibrinogen",
    "vitamin_d_ng_ml":           "Vitamin D (25-OH)",
    "vitamin_b12_pg_ml":         "Vitamin B12",
    "folate_ng_ml":              "Folate",
    "magnesium_rbc_mg_dl":       "Magnesium (RBC)",
    "zinc_ug_dl":                "Zinc",
    "lp_pla2_ng_ml":             "Lp-PLA2",
    "omega_3_index_pct":         "Omega-3 Index",
}
