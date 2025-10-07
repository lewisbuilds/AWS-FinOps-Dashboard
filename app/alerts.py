"""Alert dispatching utilities.

Initial implementation logs alerts; can be extended to Slack, Email, SNS, etc.
"""

from __future__ import annotations
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def dispatch_anomaly_alert(anomalies: List[Dict[str, Any]], context: Dict[str, Any]) -> None:
    if not anomalies:
        return
    logger.warning(
        "Cost anomalies detected",
        extra={
            "alert_type": "cost_anomaly",
            "anomaly_count": len(anomalies),
            "anomalies": anomalies[:10],  # cap log size
            "context": context,
        },
    )
