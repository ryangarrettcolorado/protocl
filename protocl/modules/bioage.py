"""Biological age — Levine PhenoAge.

Reference: Levine et al. 2018, "An epigenetic biomarker of aging for lifespan
and healthspan", Aging (Albany NY). The PhenoAge linear combination uses 9
clinical chemistry markers + chronological age. We implement the published
coefficients and convert to a Mortality Score → PhenoAge in years.

PhenoAge biomarkers (all must be present):
- albumin       (g/L)   — note: lab values usually in g/dL × 10
- creatinine    (umol/L)— lab values usually in mg/dL × 88.4
- glucose       (mmol/L)— lab values usually in mg/dL ÷ 18
- crp           (ln(mg/L))
- lymphocyte_pct (%)
- mcv            (fL)
- rdw            (%)
- alkaline_phos (U/L)
- wbc           (10^9/L) — same as 10^3/uL
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd


# ────────────────────────────────────────────────────────────────────────────
# Levine 2018 PhenoAge coefficients
# ────────────────────────────────────────────────────────────────────────────

# Each tuple: (coefficient, unit-converted name)
# Linear combo `xb` is summed; then plugged into the Gompertz form below.
COEFFS = {
    "albumin":         -0.0336,   # g/L
    "creatinine":      0.0095,    # umol/L
    "glucose":         0.1953,    # mmol/L
    "ln_crp":          0.0954,    # ln(mg/L)
    "lymphocyte_pct":  -0.0120,   # %
    "mcv":             0.0268,    # fL
    "rdw":             0.3306,    # %
    "alkaline_phos":   0.0019,    # U/L
    "wbc":             0.0554,    # 10^9/L
    "age":             0.0804,    # years
    "intercept":       -19.9067,
}

# Gompertz parameters from Levine 2018
GAMMA = 0.0076927
LAMBDA = 0.0192  # mortality score scaling
# 120-month (10yr) mortality formula:
#   M = 1 - exp(-exp(xb) * (exp(120 * GAMMA) - 1) / GAMMA)
# PhenoAge = 141.50225 + ln(-0.00553 * ln(1 - M)) / 0.090165


@dataclass
class PhenoAgeResult:
    """Result of a PhenoAge computation, with contributions for explanation."""
    pheno_age: float
    chronological_age: float
    delta: float                 # pheno - chronological
    mortality_score: float        # 10-yr mortality probability
    xb: float                    # raw linear combo
    contributions: dict          # {biomarker: contribution to xb}
    inputs_used: dict            # {biomarker: converted value used}
    missing_inputs: list         # names that were missing/None
    ok: bool                     # True only if all 9 + age were available


# ────────────────────────────────────────────────────────────────────────────
# Unit conversions — accept lab units, return Levine units
# ────────────────────────────────────────────────────────────────────────────

def _albumin_g_dl_to_g_L(v: float) -> float:    return v * 10
def _creatinine_mg_dl_to_umol_L(v: float) -> float: return v * 88.4
def _glucose_mg_dl_to_mmol_L(v: float) -> float: return v / 18.0
def _crp_mg_L_to_ln(v: float) -> float:
    # hsCRP often comes in mg/L already. Clamp tiny values to avoid -inf.
    return math.log(max(v, 0.01))


# ────────────────────────────────────────────────────────────────────────────
# Core calculation
# ────────────────────────────────────────────────────────────────────────────

def compute_phenoage(
    *,
    age_years: float,
    albumin_g_dl: Optional[float] = None,
    creatinine_mg_dl: Optional[float] = None,
    glucose_mg_dl: Optional[float] = None,
    crp_mg_L: Optional[float] = None,
    lymphocyte_pct: Optional[float] = None,
    mcv_fl: Optional[float] = None,
    rdw_pct: Optional[float] = None,
    alkaline_phos_u_l: Optional[float] = None,
    wbc_k_ul: Optional[float] = None,
) -> PhenoAgeResult:
    """Compute Levine PhenoAge from clinical lab values in everyday US units."""

    # Convert to Levine units
    converted = {
        "albumin":        _albumin_g_dl_to_g_L(albumin_g_dl) if albumin_g_dl is not None else None,
        "creatinine":     _creatinine_mg_dl_to_umol_L(creatinine_mg_dl) if creatinine_mg_dl is not None else None,
        "glucose":        _glucose_mg_dl_to_mmol_L(glucose_mg_dl) if glucose_mg_dl is not None else None,
        "ln_crp":         _crp_mg_L_to_ln(crp_mg_L) if crp_mg_L is not None else None,
        "lymphocyte_pct": lymphocyte_pct,
        "mcv":            mcv_fl,
        "rdw":            rdw_pct,
        "alkaline_phos":  alkaline_phos_u_l,
        "wbc":            wbc_k_ul,
        "age":            age_years,
    }

    missing = [k for k, v in converted.items() if v is None]

    if missing:
        return PhenoAgeResult(
            pheno_age=float("nan"),
            chronological_age=age_years,
            delta=float("nan"),
            mortality_score=float("nan"),
            xb=float("nan"),
            contributions={},
            inputs_used=converted,
            missing_inputs=missing,
            ok=False,
        )

    # Linear combination
    contributions = {k: COEFFS[k] * converted[k] for k in COEFFS if k != "intercept"}
    xb = sum(contributions.values()) + COEFFS["intercept"]

    # 10-year mortality probability (Gompertz)
    try:
        mort = 1 - math.exp(-math.exp(xb) * (math.exp(120 * GAMMA) - 1) / GAMMA)
        mort = max(min(mort, 0.999), 1e-9)
        pheno_age = 141.50225 + math.log(-0.00553 * math.log(1 - mort)) / 0.090165
    except Exception:
        mort = float("nan")
        pheno_age = float("nan")

    return PhenoAgeResult(
        pheno_age=pheno_age,
        chronological_age=age_years,
        delta=pheno_age - age_years,
        mortality_score=mort,
        xb=xb,
        contributions=contributions,
        inputs_used=converted,
        missing_inputs=[],
        ok=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# DataFrame helpers — compute PhenoAge per draw
# ────────────────────────────────────────────────────────────────────────────

def _pivot_draw(df: pd.DataFrame) -> pd.DataFrame:
    """Pivot the long-form bloodwork.csv to one row per draw_date × biomarker."""
    if df.empty:
        return df
    p = df.pivot_table(
        index="date",
        columns="biomarker_canonical",
        values="value",
        aggfunc="last",
    ).reset_index()
    return p.sort_values("date").reset_index(drop=True)


def phenoage_over_time(
    bloodwork: pd.DataFrame,
    birth_date: pd.Timestamp,
) -> pd.DataFrame:
    """For each bloodwork draw, compute PhenoAge. Returns a long-form DataFrame.

    Columns: date, chronological_age, pheno_age, delta, mortality_score, ok
    """
    pivot = _pivot_draw(bloodwork)
    if pivot.empty:
        return pd.DataFrame(columns=["date", "chronological_age", "pheno_age",
                                       "delta", "mortality_score", "ok"])

    rows = []
    for _, r in pivot.iterrows():
        draw_date = r["date"]
        age_at_draw = (draw_date - birth_date).days / 365.25
        result = compute_phenoage(
            age_years=age_at_draw,
            albumin_g_dl=r.get("albumin_g_dl"),
            creatinine_mg_dl=r.get("creatinine_mg_dl"),
            glucose_mg_dl=r.get("glucose_mg_dl"),
            crp_mg_L=r.get("hscrp_mg_l"),
            lymphocyte_pct=r.get("lymphocytes_pct"),
            mcv_fl=r.get("mcv_fl"),
            rdw_pct=r.get("rdw_pct"),
            alkaline_phos_u_l=r.get("alp_u_l"),
            wbc_k_ul=r.get("wbc_k_ul"),
        )
        rows.append({
            "date": draw_date,
            "chronological_age": result.chronological_age,
            "pheno_age": result.pheno_age,
            "delta": result.delta,
            "mortality_score": result.mortality_score,
            "ok": result.ok,
        })

    return pd.DataFrame(rows)


def latest_phenoage(
    bloodwork: pd.DataFrame,
    birth_date: pd.Timestamp,
) -> Optional[PhenoAgeResult]:
    """Compute PhenoAge from the latest draw only — returns full result with contributions."""
    pivot = _pivot_draw(bloodwork)
    if pivot.empty:
        return None
    r = pivot.iloc[-1]
    draw_date = r["date"]
    age_at_draw = (draw_date - birth_date).days / 365.25
    return compute_phenoage(
        age_years=age_at_draw,
        albumin_g_dl=r.get("albumin_g_dl"),
        creatinine_mg_dl=r.get("creatinine_mg_dl"),
        glucose_mg_dl=r.get("glucose_mg_dl"),
        crp_mg_L=r.get("hscrp_mg_l"),
        lymphocyte_pct=r.get("lymphocytes_pct"),
        mcv_fl=r.get("mcv_fl"),
        rdw_pct=r.get("rdw_pct"),
        alkaline_phos_u_l=r.get("alp_u_l"),
        wbc_k_ul=r.get("wbc_k_ul"),
    )
