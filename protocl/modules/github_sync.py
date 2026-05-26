"""GitHub sync — commit data snapshots back to the user's private health repo.

Phase 2 of the data layer: every import that lands in `data/<user>/*.csv` should
also be committed to the user's private GitHub repo. This module is the single
seam for that — pages and scripts call `commit_data_snapshot()` and never touch
the GitHub API directly.

Wiring expects three secrets (in `.streamlit/secrets.toml` or env):

    GITHUB_TOKEN  = "ghp_..."            # fine-grained PAT, repo:contents:write
    GITHUB_REPO   = "owner/repo-name"    # private repo for this user's data
    GITHUB_BRANCH = "main"               # optional, defaults to main

If any of those are missing, every function in this module silently no-ops and
returns a status dict — the rest of the app continues to function locally.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import streamlit as st
except ImportError:                              # allow CLI use without streamlit
    st = None  # type: ignore


# ────────────────────────────────────────────────────────────────────────────
# Config plumbing
# ────────────────────────────────────────────────────────────────────────────
def _secret(key: str) -> str | None:
    """Pull a secret from st.secrets, then env."""
    if st is not None:
        try:
            if key in st.secrets:
                return st.secrets[key]
        except Exception:
            pass
    return os.environ.get(key)


def get_config() -> dict:
    """Return current GitHub sync configuration. Safe to call any time."""
    return {
        "token":   _secret("GITHUB_TOKEN"),
        "repo":    _secret("GITHUB_REPO"),
        "branch":  _secret("GITHUB_BRANCH") or "main",
    }


def is_configured() -> bool:
    cfg = get_config()
    return bool(cfg["token"] and cfg["repo"])


# ────────────────────────────────────────────────────────────────────────────
# Low-level GitHub Contents API helpers
# ────────────────────────────────────────────────────────────────────────────
def _api_base(cfg: dict) -> str:
    return f"https://api.github.com/repos/{cfg['repo']}/contents"


def _headers(cfg: dict) -> dict:
    return {
        "Authorization": f"Bearer {cfg['token']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_sha(path: str, cfg: dict) -> str | None:
    """Get the current blob SHA for an existing file (None if not present)."""
    import requests
    url = f"{_api_base(cfg)}/{path}?ref={cfg['branch']}"
    r = requests.get(url, headers=_headers(cfg), timeout=15)
    if r.status_code == 200:
        return r.json().get("sha")
    return None


def put_file(path: str, content_bytes: bytes,
              message: str | None = None) -> dict:
    """Create-or-update a single file via the GitHub Contents API.

    Returns `{"ok": bool, "status": int, "message": str, "url": str | None}`.
    No-ops when not configured.
    """
    if not is_configured():
        return {"ok": False, "status": 0, "message": "github_sync not configured",
                "url": None}
    try:
        import requests
    except ImportError:
        return {"ok": False, "status": 0, "message": "requests not installed",
                "url": None}

    cfg = get_config()
    sha = _get_sha(path, cfg)
    payload: dict[str, Any] = {
        "message": message or f"Protocōl snapshot: {path} @ {datetime.utcnow().isoformat()}Z",
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": cfg["branch"],
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(f"{_api_base(cfg)}/{path}", headers=_headers(cfg),
                     json=payload, timeout=30)
    return {
        "ok": r.status_code in (200, 201),
        "status": r.status_code,
        "message": r.json().get("commit", {}).get("sha", r.text[:200]) if r.ok else r.text[:200],
        "url": r.json().get("content", {}).get("html_url") if r.ok else None,
    }


# ────────────────────────────────────────────────────────────────────────────
# High-level convenience wrappers
# ────────────────────────────────────────────────────────────────────────────
def commit_data_snapshot(data_dir: Path, user_id: str = "ryan") -> dict:
    """Push every CSV/JSON under `data/<user_id>/` up to GitHub.

    Returns a summary dict with per-file outcomes — useful both for the UI
    and for GitHub Actions log output.
    """
    user_dir = data_dir / user_id
    if not user_dir.exists():
        return {"ok": False, "reason": f"no such dir: {user_dir}", "files": []}

    results = []
    for fp in sorted(user_dir.iterdir()):
        if fp.is_file() and fp.suffix.lower() in (".csv", ".json"):
            rel_path = f"data/{user_id}/{fp.name}"
            outcome = put_file(rel_path, fp.read_bytes(),
                                message=f"chore(data): snapshot {fp.name}")
            results.append({"file": fp.name, **outcome})

    return {
        "ok": all(r.get("ok") for r in results) if results else False,
        "files": results,
        "configured": is_configured(),
    }


def status_badge_html() -> str:
    """Small HTML pill for pages that want to surface sync state."""
    if is_configured():
        return ('<span style="background:rgba(76,175,80,0.18);color:#4CAF50;'
                'padding:2px 8px;border-radius:4px;font-size:0.75rem;'
                'font-weight:600;">GITHUB SYNC LIVE</span>')
    return ('<span style="background:rgba(255,152,0,0.18);color:#FF9800;'
            'padding:2px 8px;border-radius:4px;font-size:0.75rem;'
            'font-weight:600;">GITHUB SYNC DISABLED</span>')


# ────────────────────────────────────────────────────────────────────────────
# CLI entrypoint — used by .github/workflows/snapshot.yml
# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Protocōl GitHub data sync")
    p.add_argument("--data-dir", default="data",
                    help="Path to data/ root (default: ./data)")
    p.add_argument("--user", default="ryan", help="User id (default: ryan)")
    args = p.parse_args()

    out = commit_data_snapshot(Path(args.data_dir), args.user)
    print(json.dumps(out, indent=2, default=str))
    raise SystemExit(0 if out.get("ok") else 1)
