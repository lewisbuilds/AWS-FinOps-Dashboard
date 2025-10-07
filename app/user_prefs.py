"""User preference persistence and management for the FinOps dashboard.

Stores per-user (per principal ARN) customization choices such as:
- visible widgets on Overview page
- personalized cost thresholds (daily/monthly)
- custom required tag keys
- dashboard theme preference
- default filters (services, accounts, date range preset)

Persistence Strategy:
Writes JSON documents under a `.finops_prefs/` directory (configurable later) keyed by a stable hash of the caller identity ARN.

This design avoids leaking full ARNs into filenames (privacy) and keeps cross-platform compatibility.
"""
from __future__ import annotations
import json
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging
import re

PREFS_DIR = Path('.finops_prefs')
PREFS_DIR.mkdir(exist_ok=True)

# Default preference template
DEFAULT_PREFS: Dict[str, Any] = {
    "version": 1,
    "overview_widgets": [
        "yesterday_cost",
        "tag_compliance",
        "anomalies",
        "recommendations",
        "cost_trend",
        "service_pie"
    ],
    "daily_cost_warning": None,  # override of settings; None -> use global
    "monthly_cost_warning": None,
    "required_tag_keys": None,   # comma string override
    "theme": "light",           # light | dark (Streamlit theme toggle limited)
    "default_date_range": "Last 7 days",  # Last 7/30/90 days or Custom
    "default_services": ["All"],
    "default_accounts": ["All"],
    "saved_filters": {},         # reserved for future free-form saved filter sets
    "updated_at": None
}

logger = logging.getLogger(__name__)

SANITIZE_CTRL = re.compile(r"[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f]")


def _principal_hash(principal_arn: str) -> str:
    h = hashlib.sha256(principal_arn.encode('utf-8')).hexdigest()[:16]
    return h


def _prefs_path(principal_arn: str) -> Path:
    return PREFS_DIR / f"prefs-{_principal_hash(principal_arn)}.json"


def load_prefs(principal_arn: str) -> Dict[str, Any]:
    path = _prefs_path(principal_arn)
    if not path.exists():
        prefs = DEFAULT_PREFS.copy()
        prefs['updated_at'] = datetime.utcnow().isoformat()
        return prefs
    try:
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        # Merge with defaults (fill new keys)
        merged = DEFAULT_PREFS.copy()
        merged.update(data)
        return merged
    except Exception as e:
        logger.warning(f"Failed to load prefs at {path}: {e}; using defaults")
        prefs = DEFAULT_PREFS.copy()
        prefs['updated_at'] = datetime.utcnow().isoformat()
        return prefs


def save_prefs(principal_arn: str, prefs: Dict[str, Any]) -> None:
    path = _prefs_path(principal_arn)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        merged = DEFAULT_PREFS.copy()
        merged.update(prefs)  # caller values take precedence without re-adding removed widgets
        merged['updated_at'] = datetime.utcnow().isoformat()
        tmp = path.with_suffix('.json.tmp')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump(merged, f, indent=2, sort_keys=True)
        tmp.replace(path)
    except Exception as e:
        logger.error(f"Failed to save prefs for {principal_arn}: {e}")


def apply_threshold_overrides(global_thresholds: Dict[str, Any], prefs: Dict[str, Any]) -> Dict[str, Any]:
    # global_thresholds expected keys: daily_warning, monthly_warning, anomaly_threshold
    out = dict(global_thresholds)
    if prefs.get('daily_cost_warning') is not None:
        out['daily_warning'] = prefs['daily_cost_warning']
    if prefs.get('monthly_cost_warning') is not None:
        out['monthly_warning'] = prefs['monthly_cost_warning']
    return out


def _clean_tag(tag: str) -> str:
    """Normalize a single tag key: strip whitespace & control chars; enforce length <=64.
    Returns empty string if invalid after cleaning.
    """
    t = SANITIZE_CTRL.sub("", tag).strip()
    if len(t) > 64:
        t = t[:64]
    # Basic allowed pattern (letters, numbers, separators - conservative)
    if not t or not re.match(r"^[A-Za-z0-9_.:\-/+=@]+$", t):
        return ""
    return t


def override_required_tags(global_tags: list[str], prefs: Dict[str, Any]) -> list[str]:
    if prefs.get('required_tag_keys'):
        parts = [p.strip() for p in str(prefs['required_tag_keys']).split(',') if p.strip()]
        cleaned = []
        for p in parts:
            ct = _clean_tag(p)
            if ct:
                cleaned.append(ct)
            if len(cleaned) >= 25:  # cap number of override tags to prevent abuse
                break
        if cleaned:
            return cleaned
    return global_tags
