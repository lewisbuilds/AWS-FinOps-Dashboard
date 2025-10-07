import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.scheduler import init_scheduler, shutdown_scheduler, list_jobs
from app.config import get_settings


def test_scheduler_disabled_does_not_start(monkeypatch):
    monkeypatch.setenv("REPORT_SCHEDULE_ENABLED", "false")
    sched = init_scheduler(force=True)
    assert sched is None
    assert list_jobs() == []


def test_scheduler_enabled_adds_job(monkeypatch):
    monkeypatch.setenv("REPORT_SCHEDULE_ENABLED", "true")
    monkeypatch.setenv("REPORT_SCHEDULE_CRON", "*/5 * * * *")  # every 5 minutes
    # Force re-read settings cache
    from app import config as cfg
    cfg.get_settings.cache_clear()  # type: ignore

    sched = init_scheduler(force=True)
    try:
        assert sched is not None
        jobs = list_jobs()
        assert len(jobs) == 1
        assert jobs[0] == "scheduled_finops_report"
    finally:
        shutdown_scheduler()


def test_scheduler_idempotent(monkeypatch):
    monkeypatch.setenv("REPORT_SCHEDULE_ENABLED", "true")
    from app import config as cfg
    cfg.get_settings.cache_clear()  # type: ignore
    s1 = init_scheduler(force=True)
    s2 = init_scheduler()
    try:
        assert s1 is s2
    finally:
        shutdown_scheduler()
