"""Tests for notifications.send_email (mock Gmail)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "protocl"))


@pytest.fixture(autouse=True)
def fake_gmail_env(monkeypatch):
    monkeypatch.setenv("GMAIL_USER", "test@example.com")
    monkeypatch.setenv("GMAIL_APP_PASSWORD", "fake_app_pw")
    yield


def test_send_email_uses_injected_smtp_fn():
    from modules.notifications import send_email

    captured = {}
    def fake_send(msg):
        captured["from"] = msg["From"]
        captured["to"] = msg["To"]
        captured["subject"] = msg["Subject"]

    ok = send_email(
        to="rgarrettcolorado@gmail.com",
        subject="Test",
        html_body="<p>hi</p>",
        markdown_body="hi",
        smtp_send_fn=fake_send,
    )
    assert ok is True
    assert captured["to"] == "rgarrettcolorado@gmail.com"
    assert captured["subject"] == "Test"
    assert captured["from"] == "test@example.com"


def test_send_email_returns_false_when_not_configured(monkeypatch):
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    from modules import notifications
    # Drop secrets too
    monkeypatch.setattr(notifications, "_get_secret", lambda k: None)
    ok = notifications.send_email("a@b.com", "s", "<p>h</p>", "h",
                                    smtp_send_fn=lambda m: None)
    assert ok is False


def test_compose_weekly_digest_runs():
    from modules.notifications import compose_weekly_digest
    subject, md = compose_weekly_digest()
    assert "Protocōl Weekly" in subject
    assert "## 🟢 Wins" in md
    assert "## 🟡 Watchlist" in md
    assert "## 🔴 Action items" in md
    assert "## 📊 Numbers" in md


def test_first_digest_creates_draft(tmp_path, monkeypatch):
    from modules import notifications
    # Redirect data dir to tmp_path
    monkeypatch.setattr(notifications, "_state_path",
                         lambda user_id="ryan": tmp_path / "state.json")
    monkeypatch.setattr(notifications, "create_draft",
                         lambda to, subj, html, md, user_id="ryan": tmp_path / "draft.html")
    # No Gmail config -> would fail; but draft path is first
    result = notifications.send_weekly_digest(to="x@y.com", user_id="ryan")
    assert result["status"] == "draft"
