"""Report scheduling module.

Initial lightweight integration of APScheduler for periodic report generation.
Focused on:
- Idempotent global scheduler instance
- Cron-based job from settings (if enabled)
- Graceful start/stop APIs
- Narrow responsibility: scheduling only (no email dispatch yet)

This was built with accessibility in mind, but manual review & testing for operational
suitability is still recommended.
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional, List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import get_settings
from .export import generate_report
from .finops import FinOpsAnalyzer  # Assuming existing analyzer class

_logger = logging.getLogger(__name__)

# Global references (protected by a simple lock for idempotent init)
_scheduler: Optional[BackgroundScheduler] = None
_lock = threading.Lock()
_job_id = "scheduled_finops_report"

def _build_analyzer() -> FinOpsAnalyzer:
    # In future we may inject dependencies/cache etc. For now instantiate directly.
    return FinOpsAnalyzer()

def _run_report_job():
    settings = get_settings()
    try:
        analyzer = _build_analyzer()
        formats = settings.report_formats_list
        output_dir = settings.report_output_dir
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        generate_report(
            analyzer,
            formats=formats,
            output_dir=output_dir,
            preset="previous_full_month",  # default periodic window; could be configurable later
        )
        _logger.info("Scheduled report generated: formats=%s output_dir=%s", formats, output_dir)
    except Exception as exc:  # pragma: no cover - defensive logging
        _logger.exception("Scheduled report generation failed: %s", exc)

def init_scheduler(force: bool = False) -> Optional[BackgroundScheduler]:
    """Initialize background scheduler if scheduling is enabled.

    Returns the scheduler instance or None if disabled.
    Idempotent unless force=True.
    """
    global _scheduler
    settings = get_settings()
    if not settings.report_schedule_enabled:
        _logger.info("Report scheduling disabled by configuration")
        return None

    with _lock:
        if _scheduler and not force:
            return _scheduler
        if _scheduler and force:
            try:
                _scheduler.shutdown(wait=False)
            except Exception:  # pragma: no cover
                pass
            _scheduler = None

        _scheduler = BackgroundScheduler(timezone=settings.report_schedule_timezone)

        cron_expr = settings.report_schedule_cron or "0 2 * * *"  # default: daily 02:00 UTC
        try:
            minute, hour, day, month, dow = cron_expr.split()
        except ValueError:
            raise ValueError("Invalid report_schedule_cron (expect 5 space-separated fields)")

        trigger = CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)
        _scheduler.add_job(_run_report_job, trigger=trigger, id=_job_id, replace_existing=True)
        _scheduler.start()
        _logger.info("Report scheduler initialized with cron=%s timezone=%s", cron_expr, settings.report_schedule_timezone)
        return _scheduler

def list_jobs() -> List[str]:
    if not _scheduler:
        return []
    return [job.id for job in _scheduler.get_jobs()]

def shutdown_scheduler(wait: bool = False):
    global _scheduler
    with _lock:
        if _scheduler:
            try:
                _scheduler.shutdown(wait=wait)
                _logger.info("Report scheduler shut down")
            except Exception:  # pragma: no cover
                _logger.exception("Error shutting down scheduler")
            finally:
                _scheduler = None
