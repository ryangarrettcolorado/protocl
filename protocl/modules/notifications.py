"""Email notifications — weekly digest + urgent alert paths.

This module composes markdown content, renders it to clean HTML, and ships
it via Gmail. Two ways to provide credentials:

  1. `st.secrets["GMAIL_APP_PASSWORD"]` + `st.secrets["GMAIL_USER"]`
     (cleaner local dev — recommended).
  2. Env vars `GMAIL_USER` / `GMAIL_APP_PASSWORD`.

When neither is configured, `send_email()` returns False and the caller can
fall back to writing the digest to disk for manual review.

**Safety:** the FIRST send of any weekly digest is created as a Gmail draft
(`create_draft`) rather than sent directly. Once Ryan reviews the inaugural
draft, the gate flips and subsequent digests send live. The gate is stored
in `data/<user>/notifications_state.json`.
"""
from __future__ import annotations

import base64
import json
import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import pandas as pd

from modules.data_loader import DATA_DIR, DEFAULT_USER, load_data


STATE_FILE = "notifications_state.json"


def _state_path(user_id: str = DEFAULT_USER) -> Path:
    return DATA_DIR / user_id / STATE_FILE


def _load_state(user_id: str = DEFAULT_USER) -> dict[str, Any]:
    p = _state_path(user_id)
    if not p.exists():
        return {"first_digest_sent": False, "last_critical_sent": {}}
    try:
        with p.open() as f:
            return json.load(f)
    except Exception:
        return {"first_digest_sent": False, "last_critical_sent": {}}


def _save_state(state: dict, user_id: str = DEFAULT_USER) -> None:
    p = _state_path(user_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(state, f, indent=2)


def _get_secret(key: str) -> str | None:
    try:
        import streamlit as st  # imported lazily so this module is usable outside Streamlit
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key)


def is_configured() -> bool:
    return bool(_get_secret("GMAIL_USER") and _get_secret("GMAIL_APP_PASSWORD"))


# ──────────────────────────────────────────────────────────────────────────
# Markdown → HTML
# ──────────────────────────────────────────────────────────────────────────

def _md_to_html(md: str) -> str:
    """Very small markdown subset: headings, bold, lists, paragraphs."""
    try:
        import markdown
        return markdown.markdown(md, extensions=["tables"])
    except ImportError:
        # Minimal fallback — escape and convert basic newlines
        import html
        escaped = html.escape(md)
        lines = []
        for line in escaped.split("\n"):
            if line.startswith("# "):
                lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                lines.append(f"<h2>{line[3:]}</h2>")
            elif line.startswith("- "):
                lines.append(f"<li>{line[2:]}</li>")
            else:
                lines.append(f"<p>{line}</p>")
        return "<html><body>" + "\n".join(lines) + "</body></html>"


# ──────────────────────────────────────────────────────────────────────────
# Send / draft
# ──────────────────────────────────────────────────────────────────────────

def send_email(to: str, subject: str, html_body: str, markdown_body: str,
               smtp_send_fn=None) -> bool:
    """Send a plain SMTP message via Gmail (TLS, port 587).

    `smtp_send_fn` is dependency injection for tests — when provided, it's
    called with (msg) instead of opening a real SMTP connection.
    """
    user = _get_secret("GMAIL_USER")
    pw = _get_secret("GMAIL_APP_PASSWORD")
    if not user or not pw:
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.attach(MIMEText(markdown_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    if smtp_send_fn is not None:
        smtp_send_fn(msg)
        return True
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True
    except Exception:
        return False


def create_draft(to: str, subject: str, html_body: str, markdown_body: str,
                 user_id: str = DEFAULT_USER) -> Path:
    """Write a draft to disk for review. Returns path to the draft file.

    Used for the FIRST digest as a safety gate — Ryan reads it, confirms,
    then flips `first_digest_sent=True` in notifications_state.json.
    """
    draft_dir = DATA_DIR / user_id / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    draft_path = draft_dir / f"digest_draft_{ts}.html"
    with draft_path.open("w") as f:
        f.write(f"<!-- To: {to} -->\n")
        f.write(f"<!-- Subject: {subject} -->\n")
        f.write(html_body)
    md_path = draft_path.with_suffix(".md")
    with md_path.open("w") as f:
        f.write(f"To: {to}\nSubject: {subject}\n\n{markdown_body}")
    return draft_path


# ──────────────────────────────────────────────────────────────────────────
# Digest composition
# ──────────────────────────────────────────────────────────────────────────

def compose_weekly_digest(user_id: str = DEFAULT_USER) -> tuple[str, str]:
    """Return (subject, markdown_body) for this week's digest."""
    from modules.alerts import evaluate_all_alerts, SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO

    data = load_data(user_id)
    today = datetime.now().date()
    monday = today - timedelta(days=today.weekday())
    subject = f"Protocōl Weekly — Week of {monday.strftime('%b %d')}"

    alerts = evaluate_all_alerts(user_id)
    critical = [a for a in alerts if a.severity == SEVERITY_CRITICAL]
    warnings = [a for a in alerts if a.severity == SEVERITY_WARNING]
    infos    = [a for a in alerts if a.severity == SEVERITY_INFO]

    # Numbers block
    w = data.wearables
    sleep_avg = hrv_avg = rhr_avg = "—"
    if not w.empty:
        last7 = w.sort_values("date").tail(7)
        if "sleep_duration_hrs" in last7.columns and last7["sleep_duration_hrs"].notna().any():
            sleep_avg = f"{last7['sleep_duration_hrs'].mean():.1f}h"
        if "hrv_sdnn_ms" in last7.columns and last7["hrv_sdnn_ms"].notna().any():
            hrv_avg = f"{last7['hrv_sdnn_ms'].mean():.0f} ms"
        if "resting_hr_bpm" in last7.columns and last7["resting_hr_bpm"].notna().any():
            rhr_avg = f"{last7['resting_hr_bpm'].mean():.0f} bpm"

    training_hours = "—"
    if not data.training.empty and "duration_min" in data.training.columns:
        wk_train = data.training[
            pd.to_datetime(data.training["date"], errors="coerce") >= pd.Timestamp(monday)
        ]
        training_hours = f"{wk_train['duration_min'].sum() / 60:.1f}h"

    bw = data.bloodwork
    weight = "—"
    if not bw.empty and "weight_lbs" in w.columns:
        s = w["weight_lbs"].dropna()
        if not s.empty:
            weight = f"{s.iloc[-1]:.1f} lbs"

    # Wins
    wins = []
    if not w.empty and "hrv_sdnn_ms" in w.columns:
        last7_hrv = w.sort_values("date").tail(7)["hrv_sdnn_ms"].dropna()
        prev7_hrv = w.sort_values("date").tail(14).head(7)["hrv_sdnn_ms"].dropna()
        if not last7_hrv.empty and not prev7_hrv.empty:
            d = last7_hrv.mean() - prev7_hrv.mean()
            if d > 1.5:
                wins.append(f"HRV up {d:+.1f} ms week-over-week")
    if not w.empty and "sleep_duration_hrs" in w.columns:
        last7_sleep = w.sort_values("date").tail(7)["sleep_duration_hrs"].dropna()
        if not last7_sleep.empty and last7_sleep.mean() >= 7.5:
            wins.append(f"Sleep average: {last7_sleep.mean():.1f}h (≥7.5h target)")
    if not wins:
        wins.append("Routine on track — keep going.")

    # Build markdown
    lines = [
        f"# {subject}",
        "",
        "## 🟢 Wins this week",
    ]
    for w_line in wins:
        lines.append(f"- {w_line}")

    lines += ["", "## 🟡 Watchlist"]
    if warnings:
        for a in warnings:
            lines.append(f"- **{a.title}** — {a.body}")
    else:
        lines.append("- No active warnings.")

    lines += ["", "## 🔴 Action items"]
    if critical:
        for a in critical:
            lines.append(f"- **{a.title}** — {a.body}"
                          + (f" → _{a.action}_" if a.action else ""))
    else:
        lines.append("- No critical alerts.")

    lines += [
        "",
        "## 📊 Numbers",
        "",
        "| Metric | This week |",
        "|---|---|",
        f"| Sleep avg | {sleep_avg} |",
        f"| HRV avg | {hrv_avg} |",
        f"| RHR avg | {rhr_avg} |",
        f"| Training hours | {training_hours} |",
        f"| Bodyweight | {weight} |",
        "",
        "## 💡 Recommendations",
    ]
    if critical or warnings:
        top = (critical + warnings)[:2]
        for a in top:
            lines.append(f"- {a.action or 'Review ' + a.title}: {a.body}")
    else:
        lines.append("- Maintain current protocol — biomarkers in range, recovery on target.")

    lines += [
        "",
        "## 📅 This week",
    ]
    if infos:
        for a in infos[:5]:
            lines.append(f"- {a.title}")
    else:
        lines.append("- No scheduled items.")

    lines += [
        "",
        "---",
        "Reply to this email to add a note to your journal. _(Reply parsing not yet wired in v3.1.)_",
    ]
    return subject, "\n".join(lines)


def send_weekly_digest(to: str | None = None, user_id: str = DEFAULT_USER,
                       force_send: bool = False) -> dict[str, Any]:
    """Build the weekly digest and either send or draft it.

    Returns dict {"status": "sent" | "draft" | "skipped", "path": Path | None,
    "subject": str}.
    """
    state = _load_state(user_id)
    subject, md = compose_weekly_digest(user_id)
    html = _md_to_html(md)
    to = to or _get_secret("GMAIL_USER") or "rgarrettcolorado@gmail.com"

    if not state.get("first_digest_sent") and not force_send:
        draft_path = create_draft(to, subject, html, md, user_id)
        # NB: we don't auto-flip the gate — Ryan flips it after reviewing.
        return {"status": "draft", "path": draft_path, "subject": subject}

    ok = send_email(to, subject, html, md)
    if ok:
        state["last_digest_sent"] = datetime.now().isoformat()
        _save_state(state, user_id)
        return {"status": "sent", "path": None, "subject": subject}
    return {"status": "skipped", "path": None, "subject": subject}


def send_urgent_alert(alert, to: str | None = None,
                       user_id: str = DEFAULT_USER) -> bool:
    """Fire a same-day email for a single critical alert. 12h dedupe."""
    state = _load_state(user_id)
    last = state.get("last_critical_sent", {}) or {}
    last_ts = last.get(alert.id)
    if last_ts:
        try:
            if datetime.now() - datetime.fromisoformat(last_ts) < timedelta(hours=12):
                return False
        except Exception:
            pass

    subject = f"🚨 Protocōl alert: {alert.title}"
    md = (
        f"# Critical alert\n\n"
        f"**{alert.title}**\n\n"
        f"{alert.body}\n\n"
    )
    if alert.action:
        md += f"_Action: {alert.action}_\n"
    html = _md_to_html(md)
    to = to or _get_secret("GMAIL_USER") or "rgarrettcolorado@gmail.com"
    ok = send_email(to, subject, html, md)
    if ok:
        last[alert.id] = datetime.now().isoformat()
        state["last_critical_sent"] = last
        _save_state(state, user_id)
    return ok


def mark_first_digest_reviewed(user_id: str = DEFAULT_USER) -> None:
    """Flip the gate so subsequent digests send live."""
    state = _load_state(user_id)
    state["first_digest_sent"] = True
    _save_state(state, user_id)
