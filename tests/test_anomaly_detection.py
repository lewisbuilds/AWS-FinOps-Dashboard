import math
import pytest

from app.anomaly_detection import CostAnomalyDetector, _compute_zscores


def test_zscore_basic():
    values = [10, 11, 9, 10, 10, 50]  # last is an outlier
    zscores = _compute_zscores(values)
    assert len(zscores) == len(values)
    # Outlier should have largest absolute z-score
    max_idx = max(range(len(values)), key=lambda i: abs(zscores[i]))
    assert max_idx == len(values) - 1


def test_detector_zscore_only():
    series = [
        {"date": f"2024-01-{i:02d}", "value": 100.0 + (i % 3)} for i in range(1, 21)
    ]
    # Inject anomaly
    series.append({"date": "2024-01-21", "value": 300.0})
    detector = CostAnomalyDetector(zscore_threshold=2.0, iforest_contamination=0.1, method="zscore")
    anomalies = detector.detect(series)
    assert any(a["value"] == 300.0 for a in anomalies)


@pytest.mark.skipif("sklearn" not in globals(), reason="sklearn not installed in test env")
def test_detector_iforest():  # pragma: no cover - depends on sklearn presence
    series = [
        {"date": f"2024-02-{i:02d}", "value": 100.0 + (i % 4)} for i in range(1, 40)
    ]
    series.append({"date": "2024-02-40", "value": 500.0})
    det = CostAnomalyDetector(zscore_threshold=10.0, iforest_contamination=0.05, method="iforest")
    anomalies = det.detect(series)
    assert anomalies


def test_detector_min_points_guard():
    det = CostAnomalyDetector(zscore_threshold=1.0, iforest_contamination=0.1, method="zscore")
    # FinOpsAnalyzer wrapper enforces min points; here just verify no error on small input
    anomalies = det.detect([{"date": "2024-01-01", "value": 10.0}])
    assert anomalies == []