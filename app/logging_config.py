"""Logging configuration for the AWS FinOps Dashboard.

Provides a JSON formatter for structured logs suitable for ingestion by
log aggregators (CloudWatch, ELK, Datadog, etc.) while remaining
backwards compatible with simple console logging when JSON is disabled.
"""
from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict

DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json").lower()  # 'json' or 'plain'
SERVICE_NAME = os.getenv("SERVICE_NAME", "aws-finops-dashboard")


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter.

    Ensures consistent keys so downstream processing & search queries are
    predictable. Adds contextual extras if present on the log record.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        log: Dict[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "service": SERVICE_NAME,
        }

        # Standard extras if attached
        for attr in ("error_type", "stack_info", "exc_info", "context"):
            value = getattr(record, attr, None)
            if value:
                # exc_info is a tuple—let base formatter handle it to get traceback text
                if attr == "exc_info" and isinstance(value, tuple):
                    log["exception"] = self.formatException(value)  # type: ignore[arg-type]
                else:
                    log[attr] = value
        return json.dumps(log, ensure_ascii=False)


def _configure_root_handlers():
    root = logging.getLogger()
    # Avoid duplicate handlers in interactive/test reruns
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        # Fallback to a readable plain format
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
    root.addHandler(handler)
    root.setLevel(DEFAULT_LOG_LEVEL)


def setup_logging():
    """Idempotent logging setup used by application entrypoints.

    Safe to call multiple times (subsequent calls become no-ops). The
    function chooses JSON output by default unless LOG_FORMAT=plain.
    """
    _configure_root_handlers()


# Optional convenience for modules importing *
__all__ = ["setup_logging", "JsonFormatter"]
