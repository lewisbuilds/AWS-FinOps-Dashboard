"""Advanced cost anomaly detection utilities.

Implements statistical (Z-score) and machine learning (Isolation Forest)
approaches for detecting anomalous daily cost values. The module provides a
unified interface so the FinOps analyzer can call a single detector and apply
configured sensitivity thresholds.

Accessibility note: Logging includes structured context fields so alert output
can be parsed by downstream tools. Review for your environment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Sequence
import math
import statistics
import logging

try:  # Optional heavy dependency imported lazily
    from sklearn.ensemble import IsolationForest  # type: ignore
except Exception:  # pragma: no cover - fallback when sklearn absent
    IsolationForest = None  # type: ignore

logger = logging.getLogger(__name__)


@dataclass
class AnomalyPoint:
    date: str
    value: float
    zscore: float | None
    iforest_score: float | None
    methods_flagged: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "value": self.value,
            "zscore": self.zscore,
            "iforest_score": self.iforest_score,
            "methods_flagged": self.methods_flagged,
        }


def _compute_zscores(values: Sequence[float]) -> List[float]:
    if len(values) < 2:
        return [0.0 for _ in values]
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    if stdev == 0:
        return [0.0 for _ in values]
    return [(v - mean) / stdev for v in values]


def _isolation_forest_scores(values: Sequence[float], contamination: float) -> List[float]:
    if IsolationForest is None:  # pragma: no cover - executed when sklearn missing
        logger.warning("IsolationForest unavailable - sklearn not installed")
        return [0.0 for _ in values]
    if len(values) < 2:
        return [0.0 for _ in values]
    import numpy as np  # local import to avoid mandatory dependency at import time

    model = IsolationForest(contamination=contamination, random_state=42)
    arr = np.array(values).reshape(-1, 1)
    model.fit(arr)
    # Higher anomaly score should mean more anomalous; decision_function returns reversed sign
    raw = model.decision_function(arr)
    # Normalize to 0..1 where lower raw -> more anomalous
    min_r, max_r = float(min(raw)), float(max(raw))
    if math.isclose(min_r, max_r):
        return [0.0 for _ in raw]
    norm = [float((max_r - r) / (max_r - min_r)) for r in raw]
    return norm


class CostAnomalyDetector:
    def __init__(self, *, zscore_threshold: float, iforest_contamination: float, method: str):
        self.zscore_threshold = zscore_threshold
        self.iforest_contamination = iforest_contamination
        self.method = method

    def detect(self, series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Detect anomalies in a list of {date, value} points.

        Args:
            series: List of dicts with keys 'date' (ISO string) and 'value' (float)
        Returns:
            List of anomaly dicts
        """
        if not series:
            return []
        values = [float(p["value"]) for p in series]
        dates = [p["date"] for p in series]

        zscores: List[float] | None = None
        if self.method in {"zscore", "both"}:
            zscores = _compute_zscores(values)
        iforest_scores: List[float] | None = None
        if self.method in {"iforest", "both"}:
            iforest_scores = _isolation_forest_scores(values, self.iforest_contamination)

        anomalies: List[AnomalyPoint] = []
        for idx, val in enumerate(values):
            methods_flagged: List[str] = []
            zs = zscores[idx] if zscores is not None else None
            if zs is not None and abs(zs) >= self.zscore_threshold:
                methods_flagged.append("zscore")
            if iforest_scores is not None:
                if_score = iforest_scores[idx]
                # Heuristic: score > 0.7 indicates anomaly (normalized earlier)
                if if_score >= 0.7:
                    methods_flagged.append("iforest")
            else:
                if_score = None  # type: ignore

            if methods_flagged:
                anomalies.append(
                    AnomalyPoint(
                        date=dates[idx],
                        value=val,
                        zscore=zs,
                        iforest_score=if_score,  # type: ignore
                        methods_flagged=methods_flagged,
                    )
                )

        return [a.to_dict() for a in anomalies]
