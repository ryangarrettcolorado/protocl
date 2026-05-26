"""Clinician Summary — LLM-augmented one-page narrative for physician visits."""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st

from modules.data_loader import load_data, refresh_data, latest_bloodwork_draw, previous_bloodwork_draw
from modules.charts import COLORS, metric_card_html
from modules.bioage import latest_phenoage
from modules.llm import llm_chat, is_configured, llm_badge


st.set_page_config(page_title="Clinician Summary · Protocōl", page_icon="⚗️", layout="wide")

from modules.theme import inject_css, render_sidebar_brand
inject_css()
render_sidebar_brand()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_badge, col_refresh = st.columns([6, 1.2, 1])
with col_title:
    st.title("Clinician Summary")
    st.caption("Printable one-pager for physician or functional medicine visits")
with col_badge:
    st.markdown(f"<div style='padding-top:18px;text-align:right;'>{llm_badge()}</div>",
                unsafe_allow_html=True)
with col_refresh:
    if st.button("🔄 Refresh", use_container_width=True):
        refresh_data()

data = load_data()
TODAY = pd.Timestamp("2026-05-25")
BIRTH_DATE = pd.Timestamp("1983-11-14")
chrono_age = (TODAY - BIRTH_DATE).days / 365.25

# ────────────────────────────────────────────────────────────────────────────
# Gather facts (deterministic — these feed both demo mode AND the LLM prompt)
# ────────────────────────────────────────────────────────────────────────────
def _safe_val(df: pd.DataFrame, name: str) -> float | None:
    """Pull `value` from latest draw for biomarker `name`."""
    if df.empty:
        return None
    col = "biomarker_canonical" if "biomarker_canonical" in df.columns else (
        "biomarker" if "biomarker" in df.columns else None)
    if col is None:
        return None
    hit = df[df[col] == name]
    if hit.empty:
        return None
    try:
        return float(hit.iloc[0]["value"])
    except Exception:
        return None


latest_bw = latest_bloodwork_draw(data.bloodwork)
prev_bw   = previous_bloodwork_draw(data.bloodwork)
latest_draw_date = latest_bw["date"].max() if not latest_bw.empty else None

# Bio age
try:
    bioage = latest_phenoage(data.bloodwork, BIRTH_DATE)
except Exception:
    bioage = None

# Key biomarkers
KEY_MARKERS = [
    ("apob_mg_dl",         "ApoB",            "mg/dL", "<60 optimal"),
    ("hscrp_mg_l",         "hsCRP",           "mg/L",  "<1.0 low risk"),
    ("hematocrit_pct",     "Hematocrit",      "%",     "<52 (TRT watch)"),
    ("hba1c_pct",          "HbA1c",           "%",     "<5.4 optimal"),
    ("glucose_mg_dl",      "Fasting glucose", "mg/dL", "70-95 optimal"),
    ("fasting_insulin_uiu_ml", "Fasting insulin", "µIU/mL", "<6 optimal"),
    ("ferritin_ng_ml",     "Ferritin",        "ng/mL", "75-200 optimal"),
    ("vitamin_d_25oh_ng_ml", "Vitamin D 25-OH", "ng/mL", "40-80 optimal"),
    ("omega_3_index_pct",  "Omega-3 index",   "%",     ">8 optimal"),
    ("albumin_g_dl",       "Albumin",         "g/dL",  ">4.5 optimal"),
]
key_rows = []
for code, label, unit, target in KEY_MARKERS:
    v_now = _safe_val(latest_bw, code)
    v_prev = _safe_val(prev_bw, code)
    delta = (v_now - v_prev) if (v_now is not None and v_prev is not None) else None
    key_rows.append({"code": code, "label": label, "unit": unit, "target": target,
                     "current": v_now, "prev": v_prev, "delta": delta})

# Active protocol items
prot = data.protocol.copy() if not data.protocol.empty else pd.DataFrame()
active_prot = prot[prot["cycle_status"] == "active"] if "cycle_status" in prot.columns else prot

# Body comp (latest)
inbody_latest = data.inbody.sort_values("date").tail(1) if not data.inbody.empty else pd.DataFrame()

# Wearables 30d
wear_30 = data.wearables[data.wearables["date"] >= TODAY - pd.Timedelta(days=30)] if not data.wearables.empty else pd.DataFrame()
def _wcol(*names):
    for n in names:
        if n in wear_30.columns:
            return n
    return None

sleep_col = _wcol("sleep_duration_hrs", "sleep_hrs")
hrv_col   = _wcol("hrv_sdnn_ms", "hrv_ms")
sleep_avg = wear_30[sleep_col].mean() if sleep_col and not wear_30.empty else None
rhr_avg   = wear_30["resting_hr_bpm"].mean() if "resting_hr_bpm" in wear_30.columns and not wear_30.empty else None
hrv_avg   = wear_30[hrv_col].mean() if hrv_col and not wear_30.empty else None

# Training 30d Z2 minutes
train_30 = data.training[data.training["date"] >= TODAY - pd.Timedelta(days=30)] if not data.training.empty else pd.DataFrame()
z2_min_30 = train_30["zone2_min"].sum() if "zone2_min" in train_30.columns and not train_30.empty else None
z2_per_wk = (z2_min_30 / 4.3) if z2_min_30 is not None else None

# Open action items
open_actions = data.action_items[data.action_items["status"].isin(["open", "in_progress"])] \
    if not data.action_items.empty else pd.DataFrame()
high_pri_open = open_actions[open_actions["priority"] == "high"] if not open_actions.empty else pd.DataFrame()

# Active N=1
active_nof1 = [e for e in data.nof1_experiments if e.get("status") == "active"]

# ────────────────────────────────────────────────────────────────────────────
# KPI cards — at-a-glance
# ────────────────────────────────────────────────────────────────────────────
phenoage_str   = f"{bioage.pheno_age:.1f}" if bioage and bioage.ok else "—"
phenoage_delta = (f"{bioage.delta:+.1f}y vs chrono" if bioage and bioage.ok else "—")
phenoage_pos   = (bioage.delta < 0) if (bioage and bioage.ok) else None

apob_v   = next((r["current"] for r in key_rows if r["code"] == "apob_mg_dl"), None)
hscrp_v  = next((r["current"] for r in key_rows if r["code"] == "hscrp_mg_l"), None)
hct_v    = next((r["current"] for r in key_rows if r["code"] == "hematocrit_pct"), None)

kpis = [
    ("BIO AGE",     phenoage_str,                        phenoage_delta, phenoage_pos),
    ("CHRONO AGE",  f"{chrono_age:.1f}",                  "years",        None),
    ("APOB",        f"{apob_v:.0f}" if apob_v else "—",   "mg/dL",        (apob_v is not None and apob_v < 80)),
    ("HSCRP",       f"{hscrp_v:.2f}" if hscrp_v else "—", "mg/L",         (hscrp_v is not None and hscrp_v < 1.0)),
    ("HEMATOCRIT",  f"{hct_v:.1f}" if hct_v else "—",     "%",            (hct_v is not None and hct_v < 50)),
    ("OPEN ITEMS",  f"{len(open_actions)}",                f"{len(high_pri_open)} high pri", len(high_pri_open) == 0),
]
cols = st.columns(6)
for col, (label, value, delta, pos) in zip(cols, kpis):
    with col:
        st.markdown(metric_card_html(label, value, delta, pos), unsafe_allow_html=True)

st.markdown("---")

# ────────────────────────────────────────────────────────────────────────────
# Build the deterministic markdown summary (used in demo mode + as LLM input)
# ────────────────────────────────────────────────────────────────────────────
def _fmt_marker(r: dict) -> str:
    if r["current"] is None:
        return f"- **{r['label']}**: no recent value (target: {r['target']})"
    cur = f"{r['current']:.2f}".rstrip("0").rstrip(".")
    if r["delta"] is None:
        return f"- **{r['label']}**: {cur} {r['unit']} (target: {r['target']})"
    arrow = "↑" if r["delta"] > 0 else ("↓" if r["delta"] < 0 else "→")
    return (f"- **{r['label']}**: {cur} {r['unit']} "
            f"({arrow} {r['delta']:+.2f} vs prior draw — target: {r['target']})")


def _fmt_protocol(p: pd.DataFrame) -> str:
    if p.empty:
        return "- (no active protocol items)"
    lines = []
    for _, row in p.iterrows():
        dose = f"{row.get('dose', '')} {row.get('unit', '')}".strip()
        freq = row.get("frequency", "")
        lines.append(f"- **{row.get('name', '')}** — {dose}, {freq} ({row.get('category', '')})")
    return "\n".join(lines)


def _fmt_actions(a: pd.DataFrame) -> str:
    if a.empty:
        return "- (no open action items)"
    lines = []
    for _, row in a.head(8).iterrows():
        pri = (row.get("priority") or "").upper()
        due = row.get("due_date")
        if pd.notna(due):
            try:
                due_s = pd.to_datetime(due).strftime("%b %d")
            except Exception:
                due_s = str(due)
        else:
            due_s = "no due"
        lines.append(f"- [{pri}] {row.get('title', '')} — due {due_s}")
    return "\n".join(lines)


def _fmt_nof1(exps: list[dict]) -> str:
    if not exps:
        return "- (no active N=1 experiments)"
    lines = []
    for e in exps:
        iv = e.get("intervention", {})
        lines.append(f"- **{e.get('title', '')}** — {iv.get('name', '')} {iv.get('dose', '')} "
                     f"({iv.get('frequency', '')}); started {iv.get('start_date', '')}")
    return "\n".join(lines)


draw_str = latest_draw_date.strftime("%Y-%m-%d") if latest_draw_date is not None else "—"

bio_block = ""
if bioage and bioage.ok:
    bio_block = (
        f"- **PhenoAge:** {bioage.pheno_age:.1f} years  \n"
        f"- **Chronological age:** {bioage.chronological_age:.1f} years  \n"
        f"- **Delta:** {bioage.delta:+.1f} years "
        f"({'younger than chrono' if bioage.delta < 0 else 'older than chrono'})  \n"
        f"- **10-year mortality risk (model):** {bioage.mortality_score * 100:.1f}%"
    )
else:
    bio_block = "- PhenoAge not computable from current bloodwork."

body_block = ""
if not inbody_latest.empty:
    ib = inbody_latest.iloc[0]
    body_block = (
        f"- **Weight:** {ib.get('weight_lbs', '?')} lbs  \n"
        f"- **Skeletal muscle mass:** {ib.get('skeletal_muscle_mass_lbs', '?')} lbs  \n"
        f"- **Body fat:** {ib.get('body_fat_pct', '?')}%  \n"
        f"- **Visceral fat level:** {ib.get('visceral_fat_level', '?')}"
    )
else:
    body_block = "- No InBody scan on record."

recovery_block = (
    f"- **Avg sleep (30d):** {sleep_avg:.2f} hrs  \n" if sleep_avg is not None else ""
) + (
    f"- **Avg resting HR (30d):** {rhr_avg:.1f} bpm  \n" if rhr_avg is not None else ""
) + (
    f"- **Avg HRV (30d):** {hrv_avg:.1f} ms  \n" if hrv_avg is not None else ""
) + (
    f"- **Zone 2 (30d):** {z2_min_30:.0f} min total · ~{z2_per_wk:.0f} min/wk" if z2_per_wk is not None else ""
)
if not recovery_block:
    recovery_block = "- (no wearables / training data in last 30d)"

summary_md = f"""# Clinician Summary — Ryan Garrett
**Generated:** {TODAY.strftime("%b %d, %Y")}  
**Latest bloodwork draw:** {draw_str}  
**Source:** Protocōl Health Intelligence OS

---

## 1 · Biological Age
{bio_block}

## 2 · Key Biomarkers (latest vs prior draw)
{chr(10).join(_fmt_marker(r) for r in key_rows)}

## 3 · Body Composition
{body_block}

## 4 · Recovery & Cardio Dose (last 30 days)
{recovery_block}

## 5 · Active Protocol
{_fmt_protocol(active_prot)}

## 6 · Active N=1 Experiments
{_fmt_nof1(active_nof1)}

## 7 · Open High-Priority Items
{_fmt_actions(open_actions if high_pri_open.empty else high_pri_open)}

---
*This summary was generated by Protocōl — a personal health intelligence dashboard.
Biomarker thresholds reflect optimization targets and are tighter than standard
laboratory reference ranges. Use as a discussion aid; not a clinical diagnosis.*
"""

# ────────────────────────────────────────────────────────────────────────────
# Tabs — narrative + LLM + raw
# ────────────────────────────────────────────────────────────────────────────
tab_narrative, tab_llm, tab_raw, tab_about = st.tabs(
    ["📋 Narrative Summary", "🤖 LLM-generated", "🗂 Raw markdown", "ℹ️ About"]
)

with tab_narrative:
    st.markdown(summary_md)
    st.download_button(
        "⬇ Download as markdown",
        data=summary_md,
        file_name=f"protocol_clinician_summary_{TODAY.strftime('%Y%m%d')}.md",
        mime="text/markdown",
        use_container_width=True,
    )

with tab_llm:
    st.markdown("**Optional:** Have the LLM rewrite this summary in a tighter, "
                "physician-facing narrative voice with clinical reasoning.")
    if not is_configured():
        st.warning(
            "**Demo mode** — no `OPENAI_API_KEY` set. Add one to "
            "`.streamlit/secrets.toml` to enable LLM rewriting. "
            "The deterministic summary on the left is what would be sent to the model."
        )
        st.markdown("**Sample prompt that would be sent:**")
        st.code(
            "Rewrite the following Protocōl clinician summary as a tight, two-page "
            "physician-facing narrative. Lead with the bio-age finding, then group "
            "biomarkers into (a) cardiovascular, (b) metabolic, (c) inflammation, "
            "(d) hormones. Flag any value outside optimal targets. Keep all numbers "
            "verbatim. End with the three highest-leverage discussion questions for "
            "the physician.\n\n"
            "---\n"
            + summary_md[:1500] + "\n... (truncated)",
            language="markdown",
        )
    else:
        if st.button("Generate physician-facing narrative", type="primary",
                     use_container_width=True):
            with st.spinner("Asking the model…"):
                prompt = (
                    "Rewrite the following Protocōl clinician summary as a tight, two-page "
                    "physician-facing narrative. Lead with the bio-age finding, then group "
                    "biomarkers into (a) cardiovascular, (b) metabolic, (c) inflammation, "
                    "(d) hormones/recovery. Flag any value outside optimal targets. Keep "
                    "all numbers verbatim — do not invent or round. End with the three "
                    "highest-leverage discussion questions for the physician.\n\n"
                    "---\n" + summary_md
                )
                out = llm_chat(prompt, max_tokens=1200, temperature=0.2)
            st.markdown(out)
            st.download_button(
                "⬇ Download LLM narrative",
                data=out,
                file_name=f"protocol_llm_summary_{TODAY.strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

with tab_raw:
    st.caption("The exact markdown sent to the LLM (or downloaded above).")
    st.code(summary_md, language="markdown")

with tab_about:
    st.markdown("""
**What this page is.** A printable, single-source-of-truth handoff between
Protocōl and any clinician you work with — primary care, functional medicine,
or hormone specialist.

**How it's built.**
1. Pulls the latest bloodwork draw and the draw before it (deltas).
2. Computes Levine 2018 PhenoAge from the current draw.
3. Summarizes active protocol items (`cycle_status == active`).
4. Summarizes any active N=1 experiments.
5. Pulls open high-priority action items.
6. Wraps it as markdown — downloadable, or pipeable to an LLM for a
   physician-voice rewrite.

**LLM behavior.** With `OPENAI_API_KEY` set, the LLM rewrites the deterministic
summary into clinical-narrative voice. Without one, the deterministic version
is what you take to the appointment — both are valid handoffs.
    """)
