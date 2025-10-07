"""Export & Reporting utilities for FinOps Dashboard.

Provides functions to gather data from FinOpsAnalyzer and write
reports in CSV, JSON, and Excel formats, plus optional email
dispatch. Scheduling will be handled separately.
"""
from __future__ import annotations

import os
import io
import json
import logging
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Iterable, List, Dict, Any, Optional, Callable, Protocol, runtime_checkable

import pandas as pd
from jinja2 import Environment, BaseLoader, select_autoescape

from .finops import FinOpsAnalyzer
from .config import get_settings
from .exceptions import CostDataRetrievalError
from .email import send_report_email  # new import for SES integration

logger = logging.getLogger(__name__)

# ----------------------------- Date Range Helpers -----------------------------

def resolve_date_range(
    start: Optional[date] = None,
    end: Optional[date] = None,
    last_n_days: Optional[int] = None,
    preset: Optional[str] = None,
) -> tuple[date, date, str]:
    """Return (start, end, label) enforcing constraints.

    Priority: explicit start/end > preset > last_n_days > default 30 days.
    End is exclusive for cost explorer calls; we still return the date for reference.
    """
    today = date.today()
    if start and end:
        if end < start:
            raise ValueError("end date must be >= start date")
        label = f"{start.isoformat()}_{end.isoformat()}"
        return start, end, label
    if preset:
        if preset == "month_to_date":
            s = today.replace(day=1)
            return s, today, "month_to_date"
        if preset == "previous_full_month":
            first_this = today.replace(day=1)
            last_prev = first_this - timedelta(days=1)
            s = last_prev.replace(day=1)
            return s, last_prev, "previous_full_month"
        raise ValueError(f"Unknown preset: {preset}")
    if last_n_days:
        s = today - timedelta(days=last_n_days)
        return s, today, f"last_{last_n_days}_days"
    # default
    s = today - timedelta(days=30)
    return s, today, "last_30_days"

################################################################################
# Data Assembly
################################################################################

def build_datasets(analyzer: FinOpsAnalyzer, start: date, end: date) -> dict:
    """Collect core datasets for reporting.

    Returns dict with keys: costs, consolidated, anomalies, tag_compliance.
    Separation from writer logic allows easier future extension (e.g., parquet, PDF).
    """
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    try:
        costs = analyzer.get_multi_account_costs(start_dt, end_dt)
    except Exception as e:  # broad but we will log
        logger.exception("Failed multi-account cost retrieval")
        raise CostDataRetrievalError("multi-account cost failure") from e
    consolidated = analyzer.get_consolidated_billing_summary((end - start).days or 1)
    anomalies = analyzer.detect_advanced_cost_anomalies()
    tag_comp = analyzer.get_account_tag_compliance()
    return {
        "costs": costs,
        "consolidated": consolidated,
        "anomalies": anomalies,
        "tag_compliance": tag_comp,
    }

################################################################################
# Writer Interfaces & Implementations
################################################################################

@runtime_checkable
class WriterProtocol(Protocol):  # pragma: no cover - structural typing only
    def __call__(self, datasets: dict, output_dir: str, base_name: str, **kwargs) -> List[str]: ...

def _to_dataframe(datasets: dict) -> dict:
    costs_rows = []
    for acct_id, data in datasets["costs"].items():
        for svc, cost in data.get("service_breakdown", {}).items():
            costs_rows.append({
                "account_id": acct_id,
                "account_name": data.get("account_name"),
                "service": svc,
                "cost": cost,
            })
    costs_df = pd.DataFrame(costs_rows)

    anomalies_df = pd.DataFrame(datasets.get("anomalies", []))

    tag_rows = []
    for acct_id, comp in datasets.get("tag_compliance", {}).items():
        tag_rows.append({
            "account_id": acct_id,
            "account_name": comp.get("account_name"),
            "compliance_rate": comp.get("compliance_rate"),
            "total_resources": comp.get("total_resources"),
        })
    tag_df = pd.DataFrame(tag_rows)

    return {"costs": costs_df, "anomalies": anomalies_df, "tag_compliance": tag_df}

def write_csv(datasets: dict, output_dir: str, base_name: str) -> List[str]:
    frames = _to_dataframe(datasets)
    os.makedirs(output_dir, exist_ok=True)
    written: List[str] = []
    for key, df in frames.items():
        path = os.path.join(output_dir, f"{base_name}_{key}.csv")
        df.to_csv(path, index=False)
        written.append(path)
    return written

def write_json(datasets: dict, output_dir: str, base_name: str, pretty: bool = True) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{base_name}.json")
    with open(path, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(datasets, f, indent=2, default=str)
        else:
            json.dump(datasets, f, separators=(",", ":"), default=str)
    return [path]

def write_excel(datasets: dict, output_dir: str, base_name: str) -> List[str]:
    frames = _to_dataframe(datasets)
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{base_name}.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:  # type: ignore
        for sheet, df in frames.items():
            # Excel sheet name limit 31 chars
            sheet_name = sheet[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        # Consolidated summary sheet
        summary_df = pd.DataFrame([
            {
                "period_start": datasets["consolidated"]["period_start"],
                "period_end": datasets["consolidated"]["period_end"],
                "total_consolidated_cost": datasets["consolidated"]["total_consolidated_cost"],
                "account_count": datasets["consolidated"]["account_count"],
            }
        ])
        summary_df.to_excel(writer, sheet_name="Summary", index=False)
    return [path]

WRITERS: Dict[str, WriterProtocol] = {
    "csv": write_csv,
    "json": write_json,
    "xlsx": write_excel,
}

def register_writer(name: str, fn: WriterProtocol, *, override: bool = False) -> None:
    """Register a new writer implementation.

    Args:
        name: Format key (lowercase). If already present and override=False, raises ValueError.
        fn: Callable implementing the writer protocol.
        override: Allow replacing existing writer.
    """
    key = name.lower()
    if key in WRITERS and not override:
        raise ValueError(f"Writer '{key}' already registered. Pass override=True to replace.")
    WRITERS[key] = fn

def unregister_writer(name: str) -> None:
    """Remove a writer registration if present."""
    WRITERS.pop(name.lower(), None)

################################################################################
# Email Template Rendering
################################################################################
DEFAULT_EMAIL_TEMPLATE = """Subject: FinOps Report {{ label }}\n\nGenerated: {{ generated_at }} UTC\nPeriod: {{ period_start }} -> {{ period_end }}\nTotal Consolidated Cost: ${{ total_cost }}\nAccounts: {{ account_count }}\nAnomalies: {{ anomaly_count }}\n--\nThis is an automated report."""

def render_email_context(datasets: dict) -> dict:
    consolidated = datasets.get("consolidated", {})
    return {
        "period_start": consolidated.get("period_start"),
        "period_end": consolidated.get("period_end"),
        "total_cost": consolidated.get("total_consolidated_cost"),
        "account_count": consolidated.get("account_count"),
        "anomaly_count": len(datasets.get("anomalies", [])),
        "generated_at": datetime.utcnow().isoformat(),
    }

def render_email_body(datasets: dict, label: str, template: Optional[str] = None) -> str:
    env = Environment(loader=BaseLoader(), autoescape=select_autoescape())
    ctx = render_email_context(datasets)
    ctx["label"] = label
    tmpl = env.from_string(template or DEFAULT_EMAIL_TEMPLATE)
    return tmpl.render(**ctx)

################################################################################
# Orchestration
################################################################################

def generate_report(
    analyzer: Optional[FinOpsAnalyzer] = None,
    *,
    formats: Iterable[str] = ("csv", "json"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    last_n_days: Optional[int] = None,
    preset: Optional[str] = None,
    output_dir: Optional[str] = None,
    email: bool = False,
    email_template: Optional[str] = None,
) -> dict:
    settings = get_settings()
    analyzer = analyzer or FinOpsAnalyzer()
    start_time = datetime.utcnow()
    start_d, end_d, label = resolve_date_range(start, end, last_n_days, preset)
    datasets = build_datasets(analyzer, start_d, end_d)
    output_dir = output_dir or getattr(settings, "report_output_dir", "./exports")
    base_name = f"finops_report_{label}_{datetime.utcnow().strftime('%Y%m%d_%H%M%SZ')}"

    written: List[str] = []
    file_meta: List[Dict[str, Any]] = []
    for fmt in formats:
        fmt_key = fmt.lower()
        writer = WRITERS.get(fmt_key)
        if not writer:
            logger.warning("Unknown export format skipped", extra={"format": fmt_key})
            continue
        try:
            produced = writer(datasets, output_dir, base_name)
            for p in produced:
                try:
                    size = os.path.getsize(p)
                except OSError:
                    size = None
                file_meta.append({"path": p, "format": fmt_key, "size_bytes": size})
            written.extend(produced)
        except Exception:
            logger.exception("Writer failed", extra={"format": fmt_key})

    email_body = None
    if email and getattr(settings, "ses_enabled", False):
        try:
            email_body = render_email_body(datasets, label, email_template)
            send_result = send_report_email(email_body, written)
            logger.info("Email dispatch result", extra={"result": send_result})
        except Exception:
            logger.exception("Email sending failed")

    elapsed = (datetime.utcnow() - start_time).total_seconds()
    return {
        "label": label,
        "start": start_d.isoformat(),
        "end": end_d.isoformat(),
        "files": written,
        "file_meta": file_meta,
        "email_body": email_body,
        "duration_seconds": elapsed,
        "formats_requested": list(formats),
    }
