from unittest.mock import patch
from pathlib import Path

from app.email import send_report_email, build_email
from app.config import get_settings


def test_build_email_with_attachment(tmp_path):
    p = tmp_path / "sample.txt"
    p.write_text("hello")
    msg = build_email("Subject", "Body", "sender@example.com", ["r1@example.com"], [str(p)])
    assert "Subject" == msg["Subject"]
    assert msg.get_body() is not None
    # One attachment present
    assert any(part.get_filename() == "sample.txt" for part in msg.iter_attachments())


def test_send_report_email_disabled(monkeypatch):
    monkeypatch.setenv("SES_ENABLED", "false")
    from app import config as cfg
    cfg.get_settings.cache_clear()  # type: ignore
    result = send_report_email("body", [])
    assert result["sent"] is False
    assert result["reason"] == "ses_disabled"


def test_send_report_email_success(monkeypatch):
    # Minimal valid config
    monkeypatch.setenv("SES_ENABLED", "true")
    monkeypatch.setenv("SES_SENDER_EMAIL", "sender@example.com")
    monkeypatch.setenv("SES_RECIPIENT_EMAILS", "r1@example.com,r2@example.com")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    from app import config as cfg
    cfg.get_settings.cache_clear()  # type: ignore

    with patch("boto3.client") as mock_client:
        inst = mock_client.return_value
        inst.send_raw_email.return_value = {"MessageId": "abc-123"}
        result = send_report_email("body", [])
        assert result["sent"] is True
        assert result["message_id"] == "abc-123"
        inst.send_raw_email.assert_called_once()


def test_send_report_email_incomplete_config(monkeypatch):
    monkeypatch.setenv("SES_ENABLED", "true")
    monkeypatch.setenv("SES_SENDER_EMAIL", "sender@example.com")
    monkeypatch.delenv("SES_RECIPIENT_EMAILS", raising=False)
    from app import config as cfg
    cfg.get_settings.cache_clear()  # type: ignore
    result = send_report_email("body", [])
    assert result["sent"] is False
    assert result["reason"] == "incomplete_config"