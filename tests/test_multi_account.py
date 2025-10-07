import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from app.finops import FinOpsAnalyzer
from app.org_accounts import list_org_accounts
from app.aws_session import AWSSessionManager


@pytest.fixture
def mock_org_accounts(monkeypatch):
    def fake_list(_sm):
        return [
            {"id": "111111111111", "name": "Dev", "email": "dev@example.com"},
            {"id": "222222222222", "name": "Prod", "email": "prod@example.com"},
        ]
    monkeypatch.setattr("app.org_accounts.list_org_accounts", lambda sm: fake_list(sm))


@pytest.fixture
def analyzer(monkeypatch, mock_org_accounts):
    from app import org_accounts

    # Mock AWSSessionManager.get_session to avoid real STS validation
    def fake_get_session(self):
        class DummySession:
            def client(self, service_name, **kwargs):
                class DummySTS:
                    def get_caller_identity(self_inner):
                        return {"Arn": "arn:aws:iam::000000000000:user/Test"}
                return DummySTS()
        return DummySession()

    def fake_get_client(self, service_name, **kwargs):  # noqa: ARG001
        class DummyOrg:
            def get_paginator(self, name):  # noqa: ARG002
                class Paginator:
                    def paginate(self_inner):
                        return [{"Accounts": []}]
                return Paginator()
        return DummyOrg()

    monkeypatch.setattr(AWSSessionManager, 'get_session', fake_get_session, raising=True)
    monkeypatch.setattr(AWSSessionManager, 'get_client', fake_get_client, raising=True)

    class DummyClient:
        def __init__(self, acct_id):
            self.acct_id = acct_id
        def get_cost_and_usage(self, **kwargs):  # noqa: ARG002
            amount = "10.00" if self.acct_id == "111111111111" else "25.50"
            return {
                'ResultsByTime': [
                    {'Groups': [
                        {'Keys': ['Amazon EC2'], 'Metrics': {'BlendedCost': {'Amount': amount}}}
                    ]}
                ]
            }

    # Monkeypatch assume_member_role to bypass real STS
    def fake_assume(account_id, sm):  # noqa: ARG001
        class FakeSession:
            def client(self, service_name, **kwargs):  # noqa: ARG002
                return DummyClient(account_id)
        return FakeSession()

    monkeypatch.setattr(org_accounts, 'assume_member_role', fake_assume)

    def fake_iter(sm):  # noqa: ARG001
        for acct in list_org_accounts(sm):
            yield {"account": acct, "client": DummyClient(acct['id'])}

    monkeypatch.setattr(org_accounts, 'iter_account_cost_explorer_sessions', fake_iter)
    return FinOpsAnalyzer()


def test_multi_account_costs(analyzer):
    start = datetime.now() - timedelta(days=2)
    end = datetime.now() - timedelta(days=1)
    data = analyzer.get_multi_account_costs(start, end)
    assert set(data.keys()) == {"111111111111", "222222222222"}
    assert data["111111111111"]["total_cost"] == 10.00
    assert data["222222222222"]["total_cost"] == 25.50


def test_consolidated_billing_summary(analyzer):
    summary = analyzer.get_consolidated_billing_summary(days=1)
    assert summary['account_count'] == 2
    assert summary['total_consolidated_cost'] == 35.5
    assert len(summary['top_accounts']) == 2

