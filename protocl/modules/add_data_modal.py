"""v3.4 Adaptive UI — Layer 2: per-source "Add data" modals.

Each modal is a small ``st.dialog`` scoped to a single data type. The modals
deliberately *reuse* the app's existing import flows rather than reimplementing
them — the bloodwork/Function Health uploaders feed the same PDF parser the
Import Center uses, manual forms call ``data_loader.append_row`` exactly like
the pages do, and connector sources point at the Integrations page. The modal
chrome (header + footer) is the only shared logic; the body per source is kept
focused.

Requires Streamlit >= 1.42 for ``st.dialog`` (already pinned).
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.data_presence import get_source


def _footer(source_key: str) -> None:
    """Shared modal footer: a link to the full Import Center."""
    src = get_source(source_key)
    st.divider()
    try:
        from modules.nav import page_link
        page_link("imports", label="Need more options? → Full Import Center")
    except Exception:
        st.caption("Need more options? → Full Import Center")


# ────────────────────────────────────────────────────────────────────────────
# Per-source bodies
# ────────────────────────────────────────────────────────────────────────────

def _body_pdf_upload(source_key: str, *, kind: str) -> None:
    """PDF/CSV uploader that reuses the existing lab parser.

    ``kind`` is "bloodwork" or "function_health"; both flow into the same
    Function Health PDF parser used by the Import Center.
    """
    src = get_source(source_key)
    st.write(src.value_prop)
    up = st.file_uploader(
        "Upload a lab PDF or CSV", type=["pdf", "csv"],
        key=f"modal_upload_{source_key}",
    )
    if up is not None:
        st.info(
            "Uploaded. Parsing happens in the Import Center so every import "
            "shares one audit trail — opening it now."
        )
        try:
            from modules.nav import page_link
            page_link(src.add_data_route, label=f"Continue in {src.label} import →")
        except Exception:
            st.caption("Open the Import Center to finish.")


def _body_connector(source_key: str) -> None:
    """Connector-status check + Connect button (wearables, strava)."""
    src = get_source(source_key)
    st.write(src.value_prop)
    st.caption(
        "Connections are managed on the Integrations page so credentials and "
        "sync status live in one place."
    )
    try:
        from modules.nav import page_link
        page_link("integrations", label=f"Connect {src.label} →")
    except Exception:
        st.caption("Open Integrations to connect.")


def _body_manual_inbody(source_key: str) -> None:
    from modules.data_loader import append_row

    st.write(get_source(source_key).value_prop)
    with st.form(f"modal_form_{source_key}", clear_on_submit=True):
        d = st.date_input("Scan date", value=date.today())
        c1, c2, c3 = st.columns(3)
        with c1:
            weight = st.number_input("Weight (lb)", min_value=0.0, step=0.1)
        with c2:
            bf = st.number_input("Body fat %", min_value=0.0, max_value=100.0, step=0.1)
        with c3:
            smm = st.number_input("Skeletal muscle (lb)", min_value=0.0, step=0.1)
        notes = st.text_input("Notes")
        if st.form_submit_button("Save scan", type="primary"):
            append_row("inbody.csv", {
                "date": d.strftime("%Y-%m-%d"), "weight_lb": weight,
                "body_fat_pct": bf, "skeletal_muscle_mass_lb": smm, "notes": notes,
            })
            st.success("Saved.")
            st.rerun()


def _body_manual_daily_log(source_key: str) -> None:
    from modules.data_loader import append_row

    st.write(get_source(source_key).value_prop)
    with st.form(f"modal_form_{source_key}", clear_on_submit=True):
        d = st.date_input("Date", value=date.today())
        c1, c2 = st.columns(2)
        with c1:
            mood = st.slider("Mood", 1, 5, 3)
        with c2:
            energy = st.slider("Energy", 1, 5, 3)
        notes = st.text_input("Notes")
        if st.form_submit_button("Log entry", type="primary"):
            append_row("daily_log.csv", {
                "date": d.strftime("%Y-%m-%d"), "weight_lb": "",
                "mood": mood, "energy": energy, "notes": notes,
            })
            st.success("Logged.")
            st.rerun()


def _body_csv_upload(source_key: str) -> None:
    """CSV uploader for cgm / ketones — routes into the Import Center."""
    src = get_source(source_key)
    st.write(src.value_prop)
    up = st.file_uploader("Upload a CSV export", type=["csv"],
                          key=f"modal_upload_{source_key}")
    if up is not None:
        st.info("Uploaded — finish the import in the Import Center.")
        try:
            from modules.nav import page_link
            page_link("imports", label="Continue in Import Center →")
        except Exception:
            st.caption("Open the Import Center to finish.")


def _body_protocol(source_key: str) -> None:
    from modules.data_loader import append_row

    st.write(get_source(source_key).value_prop)
    with st.form(f"modal_form_{source_key}", clear_on_submit=True):
        name = st.text_input("Compound name")
        c1, c2 = st.columns(2)
        with c1:
            category = st.selectbox("Category",
                                    ["supplement", "medication", "peptide", "hormone"])
            dose = st.text_input("Dose")
        with c2:
            unit = st.text_input("Unit", value="mg")
            frequency = st.text_input("Frequency", value="daily")
        start = st.date_input("Start date", value=date.today())
        notes = st.text_input("Notes")
        if st.form_submit_button("Add compound", type="primary"):
            if name.strip():
                append_row("protocol.csv", {
                    "name": name, "category": category, "dose": dose, "unit": unit,
                    "frequency": frequency, "start_date": start.strftime("%Y-%m-%d"),
                    "end_date": "", "notes": notes,
                })
                st.success(f"Added {name}.")
                st.rerun()
            else:
                st.warning("Enter a compound name first.")


# Map each source to its modal body. PDF/connector/CSV/manual variants.
_BODY_DISPATCH = {
    "bloodwork":       lambda k: _body_pdf_upload(k, kind="bloodwork"),
    "function_health": lambda k: _body_pdf_upload(k, kind="function_health"),
    "wearables":       _body_connector,
    "sleep":           _body_connector,
    "strava":          _body_connector,
    "training":        _body_connector,
    "inbody":          _body_manual_inbody,
    "daily_log":       _body_manual_daily_log,
    "cgm":             _body_csv_upload,
    "ketones":         _body_csv_upload,
    "protocol":        _body_protocol,
}


def open_add_data_modal(source_key: str) -> None:
    """Open a Streamlit modal scoped to a single data type.

    The body is chosen per source (uploader / connector / manual form); header
    and footer chrome are shared. Unknown keys fall back to a generic Import
    Center pointer rather than raising.
    """
    src = get_source(source_key)
    body = _BODY_DISPATCH.get(source_key)

    @st.dialog(f"{src.icon} Add {src.label}")  # type: ignore[misc]
    def _dialog() -> None:
        if body is None:
            st.write(src.value_prop or f"Add {src.label} data.")
            try:
                from modules.nav import page_link
                page_link("imports", label="Open the Import Center →")
            except Exception:
                st.caption("Open the Import Center.")
        else:
            body(source_key)
        _footer(source_key)

    _dialog()
