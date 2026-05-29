"""📦 Inventory — supplements / peptides / medications.

Tracks daily dose and quantity remaining; computes days-remaining for
the alert engine. Decays automatically from last_purchase_date.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.data_loader import DATA_DIR, DEFAULT_USER, load_data
from modules.theme import inject_css


inject_css()


INVENTORY_FILE = "supplement_inventory.csv"
COLS = ["supplement_name", "daily_dose", "dose_unit",
        "quantity_remaining", "quantity_unit",
        "last_purchase_date", "last_purchase_quantity",
        "reorder_url", "notes"]


def _path() -> Path:
    return DATA_DIR / DEFAULT_USER / INVENTORY_FILE


def _load() -> pd.DataFrame:
    p = _path()
    if not p.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(p)
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    return df[COLS]


def _save(df: pd.DataFrame) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False)
    st.cache_data.clear()


def _bootstrap_from_protocol() -> pd.DataFrame:
    """Pre-populate inventory from protocol.csv supplements + medications + peptides."""
    proto = load_data().protocol
    if proto.empty:
        return pd.DataFrame(columns=COLS)
    relevant = proto[proto["category"].isin(["supplement", "medication", "peptide"])]
    rows = []
    today = date.today().isoformat()
    for _, r in relevant.iterrows():
        rows.append({
            "supplement_name": r.get("name", ""),
            "daily_dose": r.get("dose", 0),
            "dose_unit": r.get("unit", ""),
            "quantity_remaining": 30,  # rough default — 30 daily doses
            "quantity_unit": r.get("unit", ""),
            "last_purchase_date": today,
            "last_purchase_quantity": 30,
            "reorder_url": "",
            "notes": r.get("notes", ""),
        })
    return pd.DataFrame(rows, columns=COLS)


# ────────────────────────────────────────────────────────────────────────────
st.title("📦 Inventory")
st.caption("Supplements · peptides · medications · days-remaining tracking")

df = _load()

if df.empty:
    st.info("No inventory yet. You can pre-populate from your protocol stack.")
    if st.button("Bootstrap from protocol.csv"):
        df = _bootstrap_from_protocol()
        _save(df)
        st.rerun()
else:
    # Computed days_remaining
    today = date.today()
    def _days_remaining(row):
        try:
            qty = float(row["quantity_remaining"] or 0)
            dose = float(row["daily_dose"] or 0)
            if dose <= 0:
                return None
            if pd.notna(row.get("last_purchase_date")):
                lp = pd.Timestamp(row["last_purchase_date"]).date()
                last_qty = float(row.get("last_purchase_quantity") or qty)
                days_since = (today - lp).days
                qty = max(0.0, last_qty - days_since * dose)
            return qty / dose if dose > 0 else None
        except Exception:
            return None

    df["days_remaining"] = df.apply(_days_remaining, axis=1)

    st.subheader("Stock levels")
    display_cols = ["supplement_name", "daily_dose", "dose_unit",
                    "quantity_remaining", "days_remaining",
                    "last_purchase_date", "reorder_url"]
    st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Update")
    names = ["(new entry)"] + df["supplement_name"].tolist()
    pick = st.selectbox("Item", names)
    if pick == "(new entry)":
        row = {c: "" for c in COLS}
    else:
        row = df[df["supplement_name"] == pick].iloc[0].to_dict()

    c1, c2, c3 = st.columns(3)
    with c1:
        name = st.text_input("Name", row.get("supplement_name", ""))
        daily_dose = st.number_input("Daily dose", value=float(row.get("daily_dose") or 0), step=0.5)
        dose_unit = st.text_input("Dose unit", row.get("dose_unit", ""))
    with c2:
        qty_remaining = st.number_input("Quantity remaining",
                                         value=float(row.get("quantity_remaining") or 0), step=1.0)
        qty_unit = st.text_input("Quantity unit", row.get("quantity_unit", ""))
        try:
            lp_default = pd.Timestamp(row.get("last_purchase_date") or date.today()).date()
        except Exception:
            lp_default = date.today()
        lp_date = st.date_input("Last purchase date", lp_default)
    with c3:
        lp_qty = st.number_input("Last purchase quantity",
                                  value=float(row.get("last_purchase_quantity") or 0), step=1.0)
        reorder_url = st.text_input("Reorder URL", row.get("reorder_url", ""))
        notes = st.text_area("Notes", row.get("notes", ""))

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("Save", type="primary"):
            new_row = {
                "supplement_name": name,
                "daily_dose": daily_dose,
                "dose_unit": dose_unit,
                "quantity_remaining": qty_remaining,
                "quantity_unit": qty_unit,
                "last_purchase_date": lp_date.isoformat(),
                "last_purchase_quantity": lp_qty,
                "reorder_url": reorder_url,
                "notes": notes,
            }
            if pick == "(new entry)" or name not in df["supplement_name"].values:
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            else:
                df.loc[df["supplement_name"] == name, list(new_row.keys())] = list(new_row.values())
            _save(df[COLS])
            st.success("Saved.")
            st.rerun()
    with btn_col2:
        if pick != "(new entry)" and st.button("Mark as reordered (refill 30d)"):
            df.loc[df["supplement_name"] == pick, "last_purchase_date"] = date.today().isoformat()
            df.loc[df["supplement_name"] == pick, "last_purchase_quantity"] = 30 * (daily_dose or 1)
            df.loc[df["supplement_name"] == pick, "quantity_remaining"] = 30 * (daily_dose or 1)
            _save(df[COLS])
            st.rerun()
