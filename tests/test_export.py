import json
import os
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app import export as export_mod

class DummyAnalyzer:
    def get_multi_account_costs(self, start, end, granularity='DAILY'):
        return {
            '111111111111': {
                'account_id': '111111111111',
                'account_name': 'Dev',
                'total_cost': 12.34,
                'service_breakdown': {'Amazon EC2': 10.0, 'Amazon S3': 2.34}
            },
            '222222222222': {
                'account_id': '222222222222',
                'account_name': 'Prod',
                'total_cost': 56.78,
                'service_breakdown': {'Amazon EC2': 40.0, 'Amazon RDS': 16.78}
            },
        }

    def get_consolidated_billing_summary(self, days=30):
        return {
            'period_start': '2025-01-01',
            'period_end': '2025-01-31',
            'total_consolidated_cost': 69.12,
            'accounts': {},
            'top_accounts': [],
            'account_count': 2,
        }

    def detect_advanced_cost_anomalies(self):
        return [
            {'date': '2025-01-15', 'value': 123.45, 'anomaly_score': 9.9}
        ]

    def get_account_tag_compliance(self):
        return {
            '111111111111': {
                'account_id': '111111111111',
                'account_name': 'Dev',
                'compliance_rate': 95.0,
                'total_resources': 100,
                'missing_tags': {'Owner': 1}
            },
            '222222222222': {
                'account_id': '222222222222',
                'account_name': 'Prod',
                'compliance_rate': 80.0,
                'total_resources': 200,
                'missing_tags': {'CostCenter': 5}
            },
        }

@pytest.fixture()
def tmp_exports_dir(tmp_path):
    d = tmp_path / 'exports'
    d.mkdir()
    return d

@pytest.mark.parametrize('formats', [(['csv']), (['json']), (['xlsx']), (['csv','json','xlsx'])])
def test_generate_report_formats(formats, tmp_exports_dir):
    result = export_mod.generate_report(
        analyzer=DummyAnalyzer(),
        formats=formats,
        start=date(2025,1,1),
        end=date(2025,1,31),
        output_dir=str(tmp_exports_dir),
        email=False,
    )
    # basic structure
    assert 'files' in result
    for f in result['files']:
        assert os.path.exists(f)
    # Validate CSV outputs
    if 'csv' in formats:
        cost_csv = [f for f in result['files'] if f.endswith('costs.csv')]
        assert cost_csv, 'costs.csv not produced'
    # Validate JSON
    if 'json' in formats:
        json_file = [f for f in result['files'] if f.endswith('.json')][0]
        with open(json_file,'r',encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'consolidated' in data and data['consolidated']['total_consolidated_cost'] == 69.12
    # Validate Excel
    if 'xlsx' in formats:
        xlsx_file = [f for f in result['files'] if f.endswith('.xlsx')][0]
        # Read back a sheet to ensure it's written
        df_costs = pd.read_excel(xlsx_file, sheet_name='costs')
        assert not df_costs.empty


def test_resolve_date_range_priority():
    s,e,label = export_mod.resolve_date_range(start=date(2025,2,1), end=date(2025,2,10), last_n_days=7, preset='month_to_date')
    assert (s, e) == (date(2025,2,1), date(2025,2,10))
    assert '2025-02-01' in label


def test_resolve_date_range_preset_previous_full_month(monkeypatch):
    class FakeDate(date):
        @classmethod
        def today(cls):
            return date(2025,3,15)
    monkeypatch.setattr(export_mod, 'date', FakeDate)
    s,e,label = export_mod.resolve_date_range(preset='previous_full_month')
    assert (s, e) == (date(2025,2,1), date(2025,2,28))
    assert label == 'previous_full_month'


def test_email_body_render():
    dummy = DummyAnalyzer()
    datasets = export_mod.build_datasets(dummy, date(2025,1,1), date(2025,1,31))
    body = export_mod.render_email_body(datasets, 'test_label')
    assert 'FinOps Report test_label' in body
    assert 'Total Consolidated Cost' in body
