"""Settings — eight collapsible sections, persisted to user_preferences.json."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from modules.biomarker_aliases import display_name
from modules.data_loader import DATA_DIR, DEFAULT_USER
from modules.nav import load_registry
from modules.preferences import (
    PERSONA_PRESETS,
    apply_persona,
    load_preferences,
    save_preferences,
)
from modules.reference_ranges import load_reference, panel_label
from modules.theme import inject_css
from modules.charts import full_height


inject_css()

# ────────────────────────────────────────────────────────────────────────────
# Header
# ────────────────────────────────────────────────────────────────────────────
col_title, col_reset = st.columns([6, 1])
with col_title:
    st.title("Settings")
    st.caption("Profile · visible pages · home layout · ranges · data · privacy")
with col_reset:
    if st.button("↻ Reload", use_container_width=True):
        st.rerun()


prefs = load_preferences()
registry = load_registry()


# Persistent draft state — every section mutates a copy and saves explicitly.
if "prefs_draft" not in st.session_state:
    st.session_state.prefs_draft = json.loads(json.dumps(prefs))  # deep copy via JSON
draft: dict[str, Any] = st.session_state.prefs_draft


def _commit_draft(message: str = "Preferences saved.") -> None:
    save_preferences(st.session_state.prefs_draft)
    st.success(message)


# ────────────────────────────────────────────────────────────────────────────
# § 1 — Profile
# ────────────────────────────────────────────────────────────────────────────
with st.expander("👤 Profile", expanded=True):
    p = draft.setdefault("profile", {})
    c1, c2 = st.columns(2)
    with c1:
        p["display_name"] = st.text_input("Display name", value=p.get("display_name", "Ryan"))
        sex_options = ["male", "female", "other"]
        sex_idx = sex_options.index(p.get("biological_sex", "male")) if p.get("biological_sex") in sex_options else 0
        p["biological_sex"] = st.radio("Biological sex", sex_options, index=sex_idx, horizontal=True)
    with c2:
        try:
            dob_default = date.fromisoformat(p.get("date_of_birth", "1983-11-14"))
        except ValueError:
            dob_default = date(1983, 11, 14)
        dob = st.date_input("Date of birth", value=dob_default, min_value=date(1900, 1, 1))
        p["date_of_birth"] = dob.isoformat()

        TZ_OPTIONS = [
            "America/Denver", "America/Los_Angeles", "America/Chicago", "America/New_York",
            "America/Phoenix", "Europe/London", "Europe/Berlin", "Asia/Tokyo", "UTC",
        ]
        cur_tz = p.get("timezone", "America/Denver")
        if cur_tz not in TZ_OPTIONS:
            TZ_OPTIONS.insert(0, cur_tz)
        p["timezone"] = st.selectbox("Timezone", TZ_OPTIONS,
                                      index=TZ_OPTIONS.index(cur_tz))

    if st.button("Save profile", key="save_profile"):
        _commit_draft("Profile saved.")


# ────────────────────────────────────────────────────────────────────────────
# § 2 — Visible Pages (+ persona presets)
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🧭 Visible Pages", expanded=True):
    st.caption(
        "Toggle which pages appear in the top nav. Settings is always visible. "
        "Persona presets configure visibility and pinned biomarkers together."
    )

    # Persona buttons
    pc1, pc2, pc3, pc4 = st.columns(4)
    with pc1:
        if st.button("Performance", use_container_width=True):
            st.session_state.prefs_draft = apply_persona("performance", draft)
            _commit_draft("Performance persona applied.")
            st.rerun()
    with pc2:
        if st.button("Longevity", use_container_width=True):
            st.session_state.prefs_draft = apply_persona("longevity", draft)
            _commit_draft("Longevity persona applied.")
            st.rerun()
    with pc3:
        if st.button("Clinical", use_container_width=True):
            st.session_state.prefs_draft = apply_persona("clinical", draft)
            _commit_draft("Clinical persona applied.")
            st.rerun()
    with pc4:
        if st.button("Custom (clear preset)", use_container_width=True):
            draft["persona"] = "custom"
            _commit_draft("Persona set to custom.")

    st.caption(f"Current persona: **{draft.get('persona', 'custom').title()}**")
    st.divider()

    # Per-group visibility toggles
    groups_ordered = sorted(registry["groups"], key=lambda g: g.get("order", 99))
    pages_by_group: dict[str, list[dict]] = {g["id"]: [] for g in groups_ordered}
    for pg in sorted(registry["pages"], key=lambda p: p.get("order", 99)):
        pages_by_group.setdefault(pg["group"], []).append(pg)

    visible_set = set(draft.get("visible_pages", []))
    new_visible = set(visible_set)

    cols = st.columns(len(groups_ordered))
    for col, g in zip(cols, groups_ordered):
        with col:
            st.markdown(f"**{g.get('icon','')} {g['label']}**")
            for pg in pages_by_group.get(g["id"], []):
                locked = pg["id"] == "settings"
                checked = locked or (pg["id"] in visible_set)
                state = st.checkbox(
                    f"{pg.get('icon','')} {pg['title']}",
                    value=checked,
                    disabled=locked,
                    key=f"vis_{pg['id']}",
                    help="Always visible." if locked else None,
                )
                if state:
                    new_visible.add(pg["id"])
                else:
                    new_visible.discard(pg["id"])

    new_visible.add("settings")
    draft["visible_pages"] = [
        p["id"] for p in sorted(registry["pages"], key=lambda p: p.get("order", 99))
        if p["id"] in new_visible
    ]

    st.divider()
    hidden = [p["title"] for p in registry["pages"] if p["id"] not in new_visible]
    if hidden:
        st.caption(f"Hidden after save: {', '.join(hidden)}")
    else:
        st.caption("All pages visible.")

    if st.button("Save visible pages", key="save_visible"):
        _commit_draft("Visible pages saved. Reload to see the updated nav.")


# ────────────────────────────────────────────────────────────────────────────
# § 3 — Home Dashboard Layout
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🏠 Home Dashboard Layout", expanded=True):
    st.caption("Rows 1–3 (status / alerts / today's attention) are always on.")
    layout = draft.setdefault("home_layout", {})

    DEFAULT_ROWS = ["status", "alerts", "attention", "trends", "changes",
                    "recommendations", "clinician"]
    ROW_LABELS = {
        "status":          "1 · Status strip",
        "alerts":          "2 · Active alerts",
        "attention":       "3 · Today's attention",
        "trends":          "4 · Trends",
        "changes":         "5 · What changed recently",
        "recommendations": "6 · Recommendations",
        "clinician":       "7 · Clinician handoff",
    }

    rows_visible = set(layout.get("rows_visible") or DEFAULT_ROWS)
    row_order = layout.get("row_order") or DEFAULT_ROWS

    st.markdown("**Row visibility**")
    new_rows_visible = set()
    for row_id in DEFAULT_ROWS:
        locked = row_id in ("status", "alerts", "attention")
        checked = locked or (row_id in rows_visible)
        state = st.checkbox(
            ROW_LABELS[row_id], value=checked, disabled=locked,
            key=f"row_vis_{row_id}",
            help="Always on." if locked else None,
        )
        if state:
            new_rows_visible.add(row_id)
    new_rows_visible.update({"status", "alerts", "attention"})
    layout["rows_visible"] = [r for r in DEFAULT_ROWS if r in new_rows_visible]

    st.markdown("**Row order (rows 4–7)**")
    reorderable = ["trends", "changes", "recommendations", "clinician"]
    # Keep the current order but only reorderable rows can move.
    current_reorder = [r for r in row_order if r in reorderable]
    # Append any missing reorderable rows.
    for r in reorderable:
        if r not in current_reorder:
            current_reorder.append(r)

    for idx, row_id in enumerate(list(current_reorder)):
        cup, cdown, clab = st.columns([1, 1, 8])
        with cup:
            if st.button("↑", key=f"up_{row_id}", disabled=(idx == 0)):
                current_reorder[idx - 1], current_reorder[idx] = current_reorder[idx], current_reorder[idx - 1]
                layout["row_order"] = ["status", "alerts", "attention"] + current_reorder
                _commit_draft("Row order updated.")
                st.rerun()
        with cdown:
            if st.button("↓", key=f"dn_{row_id}", disabled=(idx == len(current_reorder) - 1)):
                current_reorder[idx + 1], current_reorder[idx] = current_reorder[idx], current_reorder[idx + 1]
                layout["row_order"] = ["status", "alerts", "attention"] + current_reorder
                _commit_draft("Row order updated.")
                st.rerun()
        with clab:
            st.caption(ROW_LABELS[row_id])

    layout["row_order"] = ["status", "alerts", "attention"] + current_reorder

    st.markdown("**Pinned biomarkers (max 5 on Home Row 4)**")
    ref = load_reference()
    all_bms = sorted(ref.keys())
    pretty_to_canonical = {display_name(b): b for b in all_bms}
    current_pins = layout.get("pinned_biomarkers") or []
    current_pretty = [display_name(b) for b in current_pins if b in ref]
    chosen = st.multiselect(
        "Pin up to 5 biomarkers",
        options=sorted(pretty_to_canonical.keys()),
        default=current_pretty,
        max_selections=5,
        key="pinned_multiselect",
    )
    layout["pinned_biomarkers"] = [pretty_to_canonical[name] for name in chosen]

    if st.button("Save home layout", key="save_layout"):
        _commit_draft("Home layout saved.")


# ────────────────────────────────────────────────────────────────────────────
# § 4 — Default Ranges & Targets
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🎯 Default Ranges & Targets", expanded=False):
    ranges = draft.setdefault("ranges", {})
    view_options = ["lab", "optimal", "overlay"]
    cur_view = ranges.get("default_view", "overlay")
    if cur_view not in view_options:
        cur_view = "overlay"
    ranges["default_view"] = st.radio(
        "Default range view",
        view_options,
        index=view_options.index(cur_view),
        horizontal=True,
        format_func=lambda v: {"lab": "Lab range", "optimal": "Optimal range",
                                "overlay": "Both (overlay)"}[v],
    )

    st.caption("Per-marker personal target overrides (used in charts and the Bloodwork drill-down).")
    ref = load_reference()
    targets = ranges.setdefault("personal_targets", {})

    # Build editable dataframe of every reference biomarker.
    rows = []
    for canonical, r in ref.items():
        ov = targets.get(canonical, {}) or {}
        rows.append({
            "biomarker": display_name(canonical),
            "_canonical": canonical,
            "panel": panel_label(r.get("panel", "other")),
            "lab_range": f"{r.get('lab_low','—')}–{r.get('lab_high','—')}",
            "optimal_range": f"{r.get('optimal_low','—')}–{r.get('optimal_high','—')}",
            "target_low": ov.get("low"),
            "target_high": ov.get("high"),
        })
    df = pd.DataFrame(rows).sort_values(["panel", "biomarker"])
    edited = st.data_editor(
        df.drop(columns=["_canonical"]),
        use_container_width=True,
        hide_index=True,
        disabled=["biomarker", "panel", "lab_range", "optimal_range"],
        column_config={
            "target_low":  st.column_config.NumberColumn("Personal Target Low", format="%.2f"),
            "target_high": st.column_config.NumberColumn("Personal Target High", format="%.2f"),
        },
        key="targets_editor",
    )

    if st.button("Save ranges & targets", key="save_ranges"):
        # Rebuild targets dict from edited rows.
        new_targets: dict[str, dict[str, float]] = {}
        # Re-zip edited values back to canonical keys via the original (unsorted) order.
        canonical_order = df["_canonical"].tolist()
        for canonical, (_, row) in zip(canonical_order, edited.iterrows()):
            low = row.get("target_low")
            high = row.get("target_high")
            if pd.notna(low) or pd.notna(high):
                new_targets[canonical] = {}
                if pd.notna(low):  new_targets[canonical]["low"] = float(low)
                if pd.notna(high): new_targets[canonical]["high"] = float(high)
        ranges["personal_targets"] = new_targets
        _commit_draft("Ranges & targets saved.")


# ────────────────────────────────────────────────────────────────────────────
# § 5 — Data Sources
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🗄 Data Sources", expanded=False):
    user_dir = DATA_DIR / DEFAULT_USER
    rows = []
    if user_dir.exists():
        for f in sorted(user_dir.iterdir()):
            if not f.is_file():
                continue
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            size = f.stat().st_size
            try:
                if f.suffix == ".csv":
                    rc = sum(1 for _ in f.open()) - 1
                    rc = max(0, rc)
                elif f.suffix == ".json":
                    with f.open() as fh:
                        data = json.load(fh)
                    rc = len(data) if isinstance(data, (list, dict)) else 1
                else:
                    rc = "—"
            except Exception:
                rc = "—"
            rows.append({"File": f.name, "Rows": rc,
                         "Size (KB)": f"{size/1024:.1f}", "Last modified": mtime})
    if rows:
        rows_df = pd.DataFrame(rows)
        st.dataframe(rows_df, use_container_width=True, hide_index=True,
                     height=full_height(len(rows_df)))
    else:
        st.caption(f"No data files yet under data/{DEFAULT_USER}/.")

    st.markdown(
        "**API connections** — Coming in v2: Whoop, Oura, Dexcom, Strava, Withings."
    )


# ────────────────────────────────────────────────────────────────────────────
# § 6 — Notifications (v2 stub)
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🔔 Notifications (v2 preview)", expanded=False):
    st.caption("Notifications ship with v2. Your preferences here are stored so v2 can read them.")
    notif = draft.setdefault("notifications_v2_stub", {})
    channel_opts = ["in_app", "email", "sms"]
    current_channels = notif.get("channels") or ["in_app", "email"]
    chosen_channels = []
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        if st.checkbox("In-app", value=("in_app" in current_channels), key="notif_in_app"):
            chosen_channels.append("in_app")
    with cc2:
        if st.checkbox("Email", value=("email" in current_channels), key="notif_email"):
            chosen_channels.append("email")
    with cc3:
        if st.checkbox("SMS", value=("sms" in current_channels), key="notif_sms"):
            chosen_channels.append("sms")
    notif["channels"] = chosen_channels

    severities = ["info", "warning", "critical"]
    sev = notif.get("severity_threshold", "warning")
    notif["severity_threshold"] = st.radio(
        "Severity threshold", severities,
        index=severities.index(sev) if sev in severities else 1,
        horizontal=True,
    )
    cadences = ["realtime", "daily", "weekly"]
    cad = notif.get("digest_cadence", "weekly")
    notif["digest_cadence"] = st.radio(
        "Digest cadence", cadences,
        index=cadences.index(cad) if cad in cadences else 2,
        horizontal=True,
    )

    if st.button("Save notification preferences", key="save_notif"):
        _commit_draft("Notification preferences saved.")


# ────────────────────────────────────────────────────────────────────────────
# § 7 — Privacy & Disclaimer
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🛡 Privacy & Disclaimer", expanded=False):
    disclaimer_path = Path(__file__).resolve().parent.parent / "reference" / "disclaimer.md"
    if disclaimer_path.exists():
        st.markdown(disclaimer_path.read_text())
    else:
        st.markdown(
            "**Disclaimer.** Protocōl is a personal health intelligence tool, not a "
            "medical device or diagnostic. Reference ranges throughout the app reflect "
            "functional medicine and longevity research consensus, not standard-of-care lab "
            "normals. Use the data here to inform conversations with your clinician — not to "
            "replace them."
        )

    st.divider()
    st.markdown("**Download all my data**")

    def _build_zip() -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            user_dir = DATA_DIR / DEFAULT_USER
            if user_dir.exists():
                for f in user_dir.rglob("*"):
                    if f.is_file():
                        zf.write(f, arcname=f.relative_to(DATA_DIR))
        return buf.getvalue()

    st.download_button(
        "📦 Download data bundle (.zip)",
        data=_build_zip(),
        file_name=f"protocl-data-{DEFAULT_USER}-{date.today().isoformat()}.zip",
        mime="application/zip",
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Delete account** — disabled in v1.5 (single-user, no auth).")


# ────────────────────────────────────────────────────────────────────────────
# § 8 — Theme & Appearance
# ────────────────────────────────────────────────────────────────────────────
with st.expander("🎨 Theme & Appearance", expanded=False):
    appearance = draft.setdefault("appearance", {})

    theme_opts = ["dark", "light", "system"]
    cur_theme = appearance.get("theme", "dark")
    if cur_theme not in theme_opts:
        cur_theme = "dark"
    chosen_theme = st.radio(
        "Theme", theme_opts,
        index=theme_opts.index(cur_theme),
        horizontal=True,
        help="v1.5 ships dark only. Light + system are stubs.",
    )
    appearance["theme"] = chosen_theme

    accent_opts = ["gold", "amber", "cyan"]
    cur_accent = appearance.get("accent_color", "gold")
    if cur_accent not in accent_opts:
        cur_accent = "gold"
    appearance["accent_color"] = st.selectbox(
        "Accent color", accent_opts,
        index=accent_opts.index(cur_accent),
    )

    density_opts = ["comfortable", "compact"]
    cur_density = appearance.get("density", "comfortable")
    if cur_density not in density_opts:
        cur_density = "comfortable"
    appearance["density"] = st.radio(
        "Density", density_opts,
        index=density_opts.index(cur_density),
        horizontal=True,
    )

    if st.button("Save appearance", key="save_appearance"):
        _commit_draft("Appearance saved. Reload to see density changes everywhere.")


# ────────────────────────────────────────────────────────────────────────────
# Footer — save everything
# ────────────────────────────────────────────────────────────────────────────
st.divider()
fc1, fc2 = st.columns([1, 5])
with fc1:
    if st.button("💾 Save ALL", type="primary", use_container_width=True):
        _commit_draft("All preferences saved.")
with fc2:
    st.caption("Or use each section's Save button. Settings persists to "
               f"data/{DEFAULT_USER}/user_preferences.json.")
