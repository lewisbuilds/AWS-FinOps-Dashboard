"""SES Email sending utilities for FinOps reports.

Built with accessibility in mind (clear subject/body construction) but still
requires manual validation. Provides a thin abstraction to send report emails
with optional file attachments using AWS SES.
"""
from __future__ import annotations

import os
import mimetypes
import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Optional, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .config import get_settings

logger = logging.getLogger(__name__)

MAX_TOTAL_ATTACHMENT_BYTES = 9_000_000  # leave headroom under 10MB SES raw limit


def _detect_mime(path: str) -> str:
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def build_email(subject: str, body: str, sender: str, recipients: Iterable[str], attachments: Optional[List[str]] = None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ",".join(recipients)
    msg.set_content(body)

    total_bytes = 0
    for path in attachments or []:
        try:
            data = Path(path).read_bytes()
            total_bytes += len(data)
            if total_bytes > MAX_TOTAL_ATTACHMENT_BYTES:
                logger.warning("Attachment size cap exceeded; skipping remaining attachments", extra={"cap": MAX_TOTAL_ATTACHMENT_BYTES})
                break
            maintype, subtype = _detect_mime(path).split("/", 1)
            msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=os.path.basename(path))
        except Exception:
            logger.exception("Failed reading attachment", extra={"attachment": path})
    return msg


def send_report_email(body: str, attachments: List[str]):
    settings = get_settings()
    if not settings.ses_enabled:
        logger.info("SES disabled; email skipped")
        return {"sent": False, "reason": "ses_disabled"}
    if not settings.ses_sender_email or not settings.ses_recipient_list:
        logger.warning("SES configuration incomplete; email skipped")
        return {"sent": False, "reason": "incomplete_config"}

    subject = f"FinOps Report {settings.aws_region}"  # can enhance with label if passed later
    msg = build_email(subject, body, settings.ses_sender_email, settings.ses_recipient_list, attachments)

    try:
        region = settings.ses_region or settings.aws_region
        client = boto3.client("ses", region_name=region)
        resp = client.send_raw_email(RawMessage={"Data": msg.as_bytes()})
        message_id = resp.get("MessageId")
        logger.info("SES email sent", extra={"message_id": message_id})
        return {"sent": True, "message_id": message_id}
    except (BotoCoreError, ClientError) as exc:
        logger.exception("SES send failed", extra={"error": str(exc)})
        return {"sent": False, "reason": "send_failure", "error": str(exc)}
