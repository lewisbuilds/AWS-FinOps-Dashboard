from pathlib import Path
from decimal import Decimal
import pytest
from unittest.mock import patch

from app.export import generate_report, resolve_date_range
from app.finops import FinOpsAnalyzer


class LargeDataAnalyzer(FinOpsAnalyzer):
    def get_multi_account_costs(self, start_date, end_date):  # type: ignore
        # Return > max_excel_rows rows to trigger truncation logic later (future use)
        rows = []
        for i in range(1100):  # small number; adjust if implementing row caps
            rows.append({
                "account_id": f"0000000000{i%10}",
                "date": str(start_date),
                "cost": float(Decimal("1.23")),
            })
        return rows


def test_invalid_date_range_raises(tmp_path):
    analyzer = FinOpsAnalyzer()
    # start after end should raise
    with pytest.raises(ValueError):
        generate_report(analyzer, formats=["csv"], output_dir=str(tmp_path), start="2025-02-10", end="2025-02-01")


def test_resolve_date_range_last_n_days():
    start, end, label = resolve_date_range(last_n_days=7)
    assert label == "last_7_days"
    delta = (end - start).days
    assert delta == 7  # inclusive logical span (start to end)


def test_report_generation_basic(tmp_path):
    analyzer = FinOpsAnalyzer()
    # Patch analyzer data methods to avoid external AWS dependencies
    with patch.object(analyzer, 'get_multi_account_costs', return_value={"123456789012": {"service_breakdown": {"EC2": 10.0}}}), \
         patch.object(analyzer, 'get_consolidated_billing_summary', return_value={"period_start": "2025-10-01", "period_end": "2025-10-07", "total_consolidated_cost": 10.0, "account_count": 1}), \
         patch.object(analyzer, 'detect_advanced_cost_anomalies', return_value=[]), \
         patch.object(analyzer, 'get_account_tag_compliance', return_value={"123456789012": {"account_name": "Test", "compliance_rate": 1.0, "total_resources": 5}}):
        out = generate_report(analyzer, formats=["json"], output_dir=str(tmp_path), last_n_days=2)
    assert out["label"].startswith("last_2_days")
    assert len(out["files"]) == 1
    assert out["files"][0].endswith('.json')
