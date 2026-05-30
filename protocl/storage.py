"""v3.2 — per-profile data isolation.

``ProfileStorage`` resolves every read/write to ``data/profiles/<profile_id>/``
(the owner reuses the legacy ``data/ryan/`` directory for back-compat). The
``profile_id`` is read from ``st.session_state`` and **never** accepted as a
constructor argument from page code — this is the structural guarantee that a
page cannot accidentally read another user's data.

App-wide, read-only resources (exercise libraries, reference ranges, shared
feedback/audit logs) live under ``data/shared/``. Sample seed data lives under
``data/samples/``.

When the owner is impersonating a beta user, ``read_only`` is set in session
state; every write method raises :class:`ReadOnlyError`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


DATA_DIR = Path(__file__).resolve().parent / "data"
PROFILES_DIR = DATA_DIR / "profiles"
SHARED_DIR = DATA_DIR / "shared"
SAMPLES_DIR = DATA_DIR / "samples"

# Owner keeps the pre-v3.2 single-tenant directory so real data is untouched.
OWNER_PROFILE_ID = "ryan"
OWNER_LEGACY_DIR = DATA_DIR / "ryan"

# Empty templates seeded into a brand-new beta profile so pages render cleanly.
SEED_FILES: dict[str, str] = {
    "bloodwork.csv": "date,panel,biomarker_canonical,value,unit,lab_ref_low,lab_ref_high,source_lab,notes\n",
    "protocol.csv": "name,category,dose,unit,frequency,start_date,end_date,notes\n",
    "inbody.csv": "date,weight_lb,body_fat_pct,skeletal_muscle_mass_lb,notes\n",
    "training.csv": "date,activity,duration_min,avg_hr,notes\n",
    "wearables.csv": "date,sleep_score,hrv_ms,rhr_bpm,steps,notes\n",
    "cgm_readings.csv": "datetime,glucose_mg_dl,notes\n",
    "ketone_readings.csv": "datetime,ketones_mmol_l,notes\n",
    "daily_log.csv": "date,weight_lb,mood,energy,notes\n",
    "action_items.csv": "title,category,priority,status,due_date,created_date,notes\n",
    "context_notes.csv": "date,note\n",
    "import_log.csv": "timestamp,source_type,filename,rows_imported,rows_skipped_duplicate,errors,imported_by\n",
    "nof1_experiments.json": "[]",
    "feedback.csv": "timestamp,profile_id,display_name,page,message\n",
}


class ReadOnlyError(RuntimeError):
    """Raised when a write is attempted while the storage is read-only."""


class ProfileStorage:
    """Filesystem gateway scoped to the current session's profile.

    Construct with no profile argument — the id is pulled from
    ``st.session_state.profile_id`` so page code physically cannot target
    another user's directory.
    """

    def __init__(self) -> None:
        self.profile_id: str = st.session_state.get("profile_id") or OWNER_PROFILE_ID
        self.read_only: bool = bool(st.session_state.get("read_only"))

    # ── directory resolution ────────────────────────────────────────────────
    @property
    def profile_dir(self) -> Path:
        if self.profile_id == OWNER_PROFILE_ID:
            return OWNER_LEGACY_DIR
        return PROFILES_DIR / self.profile_id

    def get_path(self, filename: str) -> Path:
        """Absolute path to ``filename`` inside the current profile dir.

        Rejects path traversal — ``filename`` must be a bare name, never a
        path that escapes the profile directory.
        """
        if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
            raise ValueError(f"unsafe filename: {filename!r}")
        return self.profile_dir / filename

    def ensure_dir(self) -> Path:
        d = self.profile_dir
        d.mkdir(parents=True, exist_ok=True)
        return d

    # ── guards ───────────────────────────────────────────────────────────────
    def _guard_write(self) -> None:
        if self.read_only:
            raise ReadOnlyError(
                f"Writes are disabled while viewing profile {self.profile_id!r} read-only."
            )

    # ── readers ───────────────────────────────────────────────────────────────
    def read_csv(self, filename: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
        path = self.get_path(filename)
        if not path.exists():
            return pd.DataFrame()
        df = pd.read_csv(path)
        for col in parse_dates or []:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df

    def read_json(self, filename: str, default: Any = None) -> Any:
        path = self.get_path(filename)
        if not path.exists():
            return [] if default is None else default
        with path.open() as f:
            return json.load(f)

    # ── writers ─────────────────────────────────────────────────────────────
    def write_csv(self, filename: str, df: pd.DataFrame) -> None:
        self._guard_write()
        path = self.get_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False)

    def append_csv(self, filename: str, row: dict) -> None:
        self._guard_write()
        path = self.get_path(filename)
        new = pd.DataFrame([row])
        if path.exists():
            new.to_csv(path, mode="a", header=False, index=False)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            new.to_csv(path, mode="w", header=True, index=False)

    def write_json(self, filename: str, payload: Any) -> None:
        self._guard_write()
        path = self.get_path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            json.dump(payload, f, indent=2, default=str)

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def exists(self) -> bool:
        return self.profile_dir.exists()

    def seed_empty(self) -> None:
        """Create the profile dir + empty templates for a new beta user."""
        self._guard_write()
        d = self.ensure_dir()
        for name, contents in SEED_FILES.items():
            target = d / name
            if not target.exists():
                target.write_text(contents)

    def load_samples(self) -> int:
        """Copy anonymized sample data into the profile (opt-in onboarding).

        Returns the number of files copied. Never overwrites existing files.
        """
        self._guard_write()
        if not SAMPLES_DIR.exists():
            return 0
        d = self.ensure_dir()
        copied = 0
        for src in SAMPLES_DIR.iterdir():
            if not src.is_file():
                continue
            dest = d / src.name
            if not dest.exists():
                shutil.copy2(src, dest)
                copied += 1
        return copied


# ────────────────────────────────────────────────────────────────────────────
# Shared (app-wide, read-only at runtime) helpers
# ────────────────────────────────────────────────────────────────────────────

def shared_path(filename: str) -> Path:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    return SHARED_DIR / filename


def append_shared_csv(filename: str, row: dict, columns: list[str]) -> None:
    """Append a row to a shared log (audit, feedback, cost). Always allowed —
    these are app-level logs, not user-scoped writable data."""
    path = shared_path(filename)
    new = pd.DataFrame([row], columns=columns)
    if path.exists():
        new.to_csv(path, mode="a", header=False, index=False)
    else:
        new.to_csv(path, mode="w", header=True, index=False)


def read_shared_csv(filename: str, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = SHARED_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for col in parse_dates or []:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df
