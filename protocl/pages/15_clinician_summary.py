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


from modules.theme import inject_css, grouped_sections
inject_css()
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

# Training 30d Z2 minutes + distance + climb
train_30 = data.training[data.training["date"] >= TODAY - pd.Timedelta(days=30)] if not data.training.empty else pd.DataFrame()
z2_min_30 = train_30["zone2_min"].sum() if "zone2_min" in train_30.columns and not train_30.empty else None
z2_per_wk = (z2_min_30 / 4.3) if z2_min_30 is not None else None
distance_30 = train_30["distance_miles"].sum() if "distance_miles" in train_30.columns and not train_30.empty else None
climb_30 = train_30["elevation_ft"].sum() if "elevation_ft" in train_30.columns and not train_30.empty else None
vo2_latest = None
if not data.wearables.empty and "vo2_max_ml_kg_min" in data.wearables.columns:
    vo2_series = data.wearables.sort_values("date")["vo2_max_ml_kg_min"].dropna()
    if not vo2_series.empty:
        vo2_latest = float(vo2_series.iloc[-1])

# Recovery score / sleep consistency (extra wearables fields for Vital Signs block)
recovery_col = _wcol("recovery_score", "recovery_pct")
sleep_consistency_avg = (
    wear_30["sleep_consistency_pct"].mean()
    if "sleep_consistency_pct" in wear_30.columns and not wear_30.empty
    else None
)
recovery_avg = (
    wear_30[recovery_col].mean()
    if recovery_col and not wear_30.empty
    else None
)

# Medications — pulled from protocol via the same keyword-inference logic 11_protocol uses.
_MED_HITS = (
    "metformin", "rapamycin", "statin", "atorvastatin", "ezetimibe",
    "ozempic", "tirzepatide", "semaglutide", "tadalafil", "finasteride",
    "sildenafil",
)
def _is_medication(category: str | None, name: str | None) -> bool:
    cat = (category or "").strip().lower()
    nm = (name or "").strip().lower()
    if cat in ("medication", "med", "drug", "pharma", "medications"):
        return True
    return any(k in nm for k in _MED_HITS)

if not active_prot.empty:
    med_mask = active_prot.apply(
        lambda r: _is_medication(r.get("category"), r.get("name")), axis=1
    )
    active_meds = active_prot[med_mask]
else:
    active_meds = pd.DataFrame()

# Risks & Alerts — simple out-of-range + suboptimal flag count from current draw.
def _gather_risk_flags(bw_df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    """Return (out_of_range_rows, suboptimal_rows) for the latest draw."""
    if bw_df.empty:
        return [], []
    try:
        from modules.reference_ranges import load_reference
        ref = load_reference()
    except Exception:
        return [], []
    out_oor, out_sub = [], []
    for _, row in bw_df.iterrows():
        canonical = row.get("biomarker_canonical")
        r = ref.get(canonical) if canonical else None
        if r is None:
            continue
        val = row.get("value")
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        lab_low, lab_high = r.get("lab_low"), r.get("lab_high")
        opt_low, opt_high = r.get("optimal_low"), r.get("optimal_high")
        entry = {"name": canonical, "value": val, "unit": r.get("unit", "")}
        if (lab_low is not None and val < lab_low) or (lab_high is not None and val > lab_high):
            out_oor.append(entry)
        elif (opt_low is not None and val < opt_low) or (opt_high is not None and val > opt_high):
            out_sub.append(entry)
    return out_oor, out_sub

oor_flags, sub_flags = _gather_risk_flags(latest_bw)

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

# Split into the spec's two sub-blocks.
vitals_block = (
    (f"- **Avg sleep (30d):** {sleep_avg:.2f} hrs  \n" if sleep_avg is not None else "")
    + (f"- **Avg resting HR (30d):** {rhr_avg:.1f} bpm  \n" if rhr_avg is not None else "")
    + (f"- **Avg HRV (30d):** {hrv_avg:.1f} ms  \n" if hrv_avg is not None else "")
    + (f"- **Avg recovery score (30d):** {recovery_avg:.0f}%  \n" if recovery_avg is not None else "")
    + (f"- **Sleep consistency (30d):** {sleep_consistency_avg:.0f}%" if sleep_consistency_avg is not None else "")
)
if not vitals_block:
    vitals_block = "- (no wearables data in last 30d)"

training_block = (
    (f"- **Zone 2 (30d):** {z2_min_30:.0f} min total · ~{z2_per_wk:.0f} min/wk  \n" if z2_per_wk is not None else "")
    + (f"- **Distance (30d):** {distance_30:.1f} miles  \n" if distance_30 is not None else "")
    + (f"- **Elevation gain (30d):** {climb_30:.0f} ft  \n" if climb_30 is not None else "")
    + (f"- **Latest VO₂max:** {vo2_latest:.1f} mL/kg/min" if vo2_latest is not None else "")
)
if not training_block:
    training_block = "- (no training data in last 30d)"

# Medications block — dedicated section pulled from active_meds.
def _fmt_medications(p: pd.DataFrame) -> str:
    if p.empty:
        return "- (no active medications)"
    lines = []
    for _, row in p.iterrows():
        dose = f"{row.get('dose', '')} {row.get('unit', '')}".strip()
        freq = row.get("frequency", "")
        lines.append(f"- **{row.get('name', '')}** — {dose}, {freq}")
    return "\n".join(lines)

# Risks & Alerts summary block.
def _fmt_risks(oor: list[dict], sub: list[dict]) -> str:
    if not oor and not sub:
        return "- (no flagged biomarkers — all in optimal range)"
    lines = []
    if oor:
        lines.append(f"**🔴 Out of lab range ({len(oor)}):**")
        for f in oor[:12]:
            lines.append(f"- {f['name']}: {f['value']:.2f} {f['unit']}")
        if len(oor) > 12:
            lines.append(f"- … and {len(oor) - 12} more")
    if sub:
        lines.append(f"\n**🟡 Suboptimal ({len(sub)}):**")
        for f in sub[:12]:
            lines.append(f"- {f['name']}: {f['value']:.2f} {f['unit']}")
        if len(sub) > 12:
            lines.append(f"- … and {len(sub) - 12} more")
    return "\n".join(lines)

header_md = (
    f"# Clinician Summary — Ryan Garrett\n"
    f"**Generated:** {TODAY.strftime('%b %d, %Y')}  \n"
    f"**Latest bloodwork draw:** {draw_str}  \n"
    f"**Source:** Protocōl Health Intelligence OS\n\n---\n"
)

footer_md = (
    "\n---\n*This summary was generated by Protocōl — a personal health intelligence "
    "dashboard. Biomarker thresholds reflect optimization targets and are tighter than "
    "standard laboratory reference ranges. Use as a discussion aid; not a clinical diagnosis.*\n"
)

# Patient notes — free text, defaults to empty. Flows into both markdown and PDF outputs.
st.markdown("**Patient notes** (free text — included in exports when 'Patient Notes' section is selected)")
patient_notes = st.text_area(
    "Patient notes",
    value="",
    height=120,
    placeholder="Symptoms, recent changes, questions for the clinician…",
    label_visibility="collapsed",
    key="patient_notes_text",
)
notes_block = patient_notes.strip() if patient_notes else "_(no notes entered)_"

SECTIONS = {
    "bio_age":      ("Biological Age",                    f"## Biological Age\n{bio_block}\n"),
    "biomarkers":   ("Key Biomarkers",                    "## Key Biomarkers (latest vs prior draw)\n" + chr(10).join(_fmt_marker(r) for r in key_rows) + "\n"),
    "body_comp":    ("Body Composition",                  f"## Body Composition\n{body_block}\n"),
    "vitals":       ("Vital Signs & Wearables",           f"## Vital Signs & Wearables (last 30 days)\n{vitals_block}\n"),
    "training":     ("Training & Performance",            f"## Training & Performance (last 30 days)\n{training_block}\n"),
    "protocol":     ("Active Protocol",                    f"## Active Protocol\n{_fmt_protocol(active_prot)}\n"),
    "medications":  ("Medications",                        f"## Medications\n{_fmt_medications(active_meds)}\n"),
    "risks":        ("Risks & Alerts",                     f"## Risks & Alerts\n{_fmt_risks(oor_flags, sub_flags)}\n"),
    "nof1":         ("Active N=1 Experiments",            f"## Active N=1 Experiments\n{_fmt_nof1(active_nof1)}\n"),
    "actions":      ("Open High-Priority Items",          f"## Open High-Priority Items\n{_fmt_actions(open_actions if high_pri_open.empty else high_pri_open)}\n"),
    "notes":        ("Patient Notes",                     f"## Patient Notes\n{notes_block}\n"),
}

st.markdown("**Sections to include**")
selected_sections = st.multiselect(
    "Pick which sections appear in the summary and exports",
    options=list(SECTIONS.keys()),
    format_func=lambda k: SECTIONS[k][0],
    default=list(SECTIONS.keys()),
    label_visibility="collapsed",
)
if not selected_sections:
    st.info("Select at least one section to build the summary.")
    selected_sections = list(SECTIONS.keys())

body_parts = [SECTIONS[k][1] for k in SECTIONS if k in selected_sections]
summary_md = header_md + "\n".join(body_parts) + footer_md

# ────────────────────────────────────────────────────────────────────────────
# Tabs — narrative + LLM + raw
# ────────────────────────────────────────────────────────────────────────────
tab_narrative, tab_llm, tab_raw, tab_about = grouped_sections(
    ["📋 Narrative Summary", "🤖 LLM-generated", "🗂 Raw markdown", "ℹ️ About"]
)

def _summary_pdf_bytes(md_text: str) -> bytes:
    """Render the markdown summary as a simple PDF via fpdf2.

    Markdown is rendered as plain text with light heading detection — fpdf2
    has no markdown parser, but the result is a clean printable handout.
    """
    try:
        from fpdf import FPDF
    except ImportError:
        return b""

    pdf = FPDF(format="letter", unit="pt")
    pdf.set_auto_page_break(auto=True, margin=54)
    pdf.add_page()
    pdf.set_margins(54, 54, 54)

    # Map common unicode glyphs to latin-1 safe equivalents BEFORE encode/replace,
    # so they render as readable characters instead of '?'.
    _GLYPH_MAP = {
        "·": "-", "—": "-", "–": "-", "→": "->", "←": "<-",
        "•": "*", "●": "*", "◦": "o",
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "≥": ">=", "≤": "<=", "≠": "!=", "±": "+/-",
        "µ": "u", "μ": "u", "\u00a0": " ", "\u200b": "",
    }

    def _safe(s: str) -> str:
        for k, v in _GLYPH_MAP.items():
            s = s.replace(k, v)
        return s.encode("latin-1", "replace").decode("latin-1")

    def _write(height: float, text: str) -> None:
        # wrapmode="CHAR" breaks inside long unbreakable tokens (URLs, hashes)
        # so fpdf2 never raises 'Not enough horizontal space to render a single character'.
        try:
            pdf.multi_cell(0, height, _safe(text), wrapmode="CHAR")
        except Exception:
            # Final safety net: hard-wrap manually if anything still slips through.
            safe = _safe(text)
            for chunk in [safe[i:i + 80] for i in range(0, len(safe), 80)] or [""]:
                try:
                    pdf.multi_cell(0, height, chunk, wrapmode="CHAR")
                except Exception:
                    pass

    for raw_line in md_text.splitlines():
        # Strip basic markdown markers for plain rendering
        clean = raw_line.replace("**", "").replace("`", "")
        if clean.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            _write(22, clean[2:])
            pdf.ln(4)
        elif clean.startswith("## "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.ln(6)
            _write(16, clean[3:])
            pdf.ln(2)
        elif clean.startswith("---"):
            pdf.ln(6)
        elif clean.strip().startswith("- "):
            pdf.set_font("Helvetica", "", 10)
            _write(14, "* " + clean.strip()[2:])
        elif clean.strip() == "":
            pdf.ln(4)
        else:
            pdf.set_font("Helvetica", "", 10)
            _write(13, clean)

    return bytes(pdf.output(dest="S"))


with tab_narrative:
    st.markdown(summary_md)
    dl_col1, dl_col2 = st.columns(2)
    with dl_col1:
        st.download_button(
            "⬇ Download as markdown",
            data=summary_md,
            file_name=f"protocol_clinician_summary_{TODAY.strftime('%Y%m%d')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with dl_col2:
        pdf_bytes = _summary_pdf_bytes(summary_md)
        if pdf_bytes:
            st.download_button(
                "⬇ Download as PDF",
                data=pdf_bytes,
                file_name=f"protocol_clinician_summary_{TODAY.strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.caption("PDF export needs `fpdf2` — install via `pip install fpdf2`.")

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
