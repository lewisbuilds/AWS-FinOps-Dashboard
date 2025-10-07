#!/usr/bin/env python
"""Permissions self-check for FinOps Dashboard.

Runs the same permission probes surfaced in the Health tab so they can be
used in CI/CD or pre-flight validation. Exits non-zero if critical FinOps
permissions are missing (currently Cost Explorer).

Usage:
  python -m scripts.permissions_check
  OR
  python scripts/permissions_check.py

Exit Codes:
  0 - All critical permissions present
  1 - One or more critical permissions missing
  2 - Unexpected runtime error
"""
from __future__ import annotations
import sys
import json
import logging
from typing import Dict

# Ensure project imports work when invoked via different working directories
try:  # pragma: no cover - defensive path handling
    from app.aws_session import AWSSessionManager
    from app.config import get_settings
except ModuleNotFoundError:  # pragma: no cover
    # Fallback: attempt to adjust path (kept minimal; prefer running from repo root)
    import pathlib, os
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root))
    from app.aws_session import AWSSessionManager  # type: ignore
    from app.config import get_settings  # type: ignore

CRITICAL_KEYS = ["cost_explorer"]  # extendable if more become hard requirements


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = get_settings()
    mgr = AWSSessionManager()

    # Establish session early to surface auth issues distinctly
    try:
        mgr.get_session()
    except Exception as e:  # pragma: no cover - integration/runtime oriented
        print(json.dumps({
            "status": "error",
            "phase": "session_init",
            "error": str(e),
            "hint": "Check credentials/profile/role configuration and run again"
        }, indent=2))
        return 2

    perms: Dict[str, bool] = mgr.validate_permissions()

    missing_critical = [k for k in CRITICAL_KEYS if not perms.get(k)]
    status = "ok" if not missing_critical else "incomplete"

    output = {
        "status": status,
        "critical_missing": missing_critical,
        "permissions": perms,
        "region": settings.aws_region,
        "auth_strategy": mgr.diagnose_credentials().get("auth_strategy"),
    }
    print(json.dumps(output, indent=2))

    if missing_critical:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    rc = main()
    sys.exit(rc)
