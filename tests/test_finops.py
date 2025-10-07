from datetime import datetime, timedelta
from decimal import Decimal


def test_get_cost_and_usage(finops_analyzer):
    start = datetime(2025, 10, 1)
    end = datetime(2025, 10, 2)
    metrics = finops_analyzer.get_cost_and_usage(start, end)
    assert metrics.total_cost == Decimal('30.0000')
    assert 'Amazon EC2' in metrics.service_breakdown
    assert metrics.service_breakdown['Amazon EC2'] == Decimal('25.0000')


def test_analyze_tag_compliance(finops_analyzer):
    compliance = finops_analyzer.analyze_tag_compliance(regions=['us-east-1'])
    assert compliance.total_resources == 2
    assert compliance.compliant_resources == 1
    assert compliance.missing_tags['Project'] >= 1
    assert compliance.compliance_rate == 50.0


def test_detect_cost_anomalies(finops_analyzer):
    anomalies = finops_analyzer.detect_cost_anomalies(days_back=7)
    assert len(anomalies) == 1
    assert anomalies[0]['anomaly_id'] == 'anomaly-1'


def test_get_cost_recommendations(finops_analyzer):
    recs = finops_analyzer.get_cost_recommendations()
    assert len(recs) == 2
    types = {r['type'] for r in recs}
    assert 'Reserved Instance' in types
    assert 'Savings Plans' in types


def test_generate_daily_report(finops_analyzer, monkeypatch):
    # Freeze time for deterministic report
    class FixedDateTime:
        @staticmethod
        def now():
            return datetime(2025, 10, 6, 12, 0, 0)

    monkeypatch.setattr('app.finops.datetime', FixedDateTime)

    report = finops_analyzer.generate_daily_report()
    assert 'cost_metrics' in report
    assert 'compliance_metrics' in report
    assert 'anomalies' in report
    assert 'recommendations' in report
    assert 'summary' in report
    assert report['summary']['anomaly_count'] >= 0
