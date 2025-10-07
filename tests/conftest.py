import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta
from app.finops import FinOpsAnalyzer
from app.aws_session import AWSSessionManager


@pytest.fixture
def mock_boto3_clients():
    """Provide mocked AWS service clients used across tests."""
    # Cost Explorer mock
    ce_client = MagicMock()
    ce_client.get_cost_and_usage.return_value = {
        'ResultsByTime': [
            {
                'TimePeriod': {
                    'Start': '2025-10-01', 'End': '2025-10-02'
                },
                'Groups': [
                    {
                        'Keys': ['Amazon EC2', '123456789012'],
                        'Metrics': {
                            'BlendedCost': {'Amount': '25.0000', 'Unit': 'USD'},
                            'UnblendedCost': {'Amount': '25.0000', 'Unit': 'USD'},
                            'UsageQuantity': {'Amount': '10', 'Unit': 'Hours'}
                        }
                    },
                    {
                        'Keys': ['Amazon S3', '123456789012'],
                        'Metrics': {
                            'BlendedCost': {'Amount': '5.0000', 'Unit': 'USD'},
                            'UnblendedCost': {'Amount': '5.0000', 'Unit': 'USD'},
                            'UsageQuantity': {'Amount': '100', 'Unit': 'GB-Mo'}
                        }
                    }
                ]
            }
        ]
    }

    ce_client.get_anomalies.return_value = {
        'Anomalies': [
            {
                'AnomalyId': 'anomaly-1',
                'AnomalyStartDate': '2025-09-30',
                'AnomalyEndDate': '2025-10-01',
                'DimensionValue': 'Amazon EC2',
                'DimensionKey': 'SERVICE',
                'RootCauses': [
                    {'Service': 'Amazon EC2', 'Region': 'us-east-1', 'LinkedAccount': '123456789012'}
                ],
                'AnomalyScore': {'CurrentScore': 90},
                'Impact': {'TotalImpact': 30.0},
                'MonitorArn': 'arn:aws:ce:us-east-1:123456789012:anomalymonitor/abc'
            }
        ]
    }

    ce_client.get_reservation_purchase_recommendation.return_value = {
        'Recommendations': [
            {
                'RecommendationDetails': {},
                'RecommendationSummary': {
                    'EstimatedMonthlySavingsAmount': '15',
                    'EstimatedMonthlyOnDemandCost': '40'
                }
            }
        ]
    }

    ce_client.get_savings_plans_purchase_recommendation.return_value = {
        'SavingsPlansRecommendationDetails': [
            {
                'EstimatedMonthlySavings': 20.0,
                'EstimatedMonthlyCommitment': 60.0
            }
        ]
    }

    # Resource Groups mock
    rg_client = MagicMock()
    rg_client.get_paginator.return_value.paginate.return_value = [
        {
            'Resources': [
                {
                    'ResourceArn': 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc',
                    'Tags': [
                        {'Key': 'Environment', 'Value': 'Prod'},
                        {'Key': 'Owner', 'Value': 'team-a'},
                        {'Key': 'Project', 'Value': 'dash'},
                        {'Key': 'CostCenter', 'Value': 'finops'}
                    ]
                },
                {
                    'ResourceArn': 'arn:aws:s3:::my-bucket',
                    'Tags': [
                        {'Key': 'Environment', 'Value': 'Dev'},
                        {'Key': 'Owner', 'Value': 'team-b'}
                    ]
                }
            ]
        }
    ]

    # STS mock
    sts_client = MagicMock()
    sts_client.get_caller_identity.return_value = {'Arn': 'arn:aws:iam::123456789012:user/test'}

    def client_factory(service_name, **kwargs):
        if service_name == 'ce':
            return ce_client
        if service_name == 'resource-groups':
            return rg_client
        if service_name == 'sts':
            return sts_client
        if service_name == 'support':
            mock = MagicMock()
            mock.describe_services.return_value = {'services': []}
            return mock
        if service_name == 'organizations':
            mock = MagicMock()
            mock.describe_organization.return_value = {'Organization': {'Arn': 'arn:aws:organizations::123456789012:organization/o-xyz'}}
            return mock
        return MagicMock()

    return {
        'ce': ce_client,
        'rg': rg_client,
        'sts': sts_client,
        'factory': client_factory
    }


class MockSession:
    def client(self, service_name, **kwargs):
        return self.factory(service_name, **kwargs)

    def get_available_regions(self, service_name):
        return ['us-east-1']


@pytest.fixture
def mock_session_manager(monkeypatch, mock_boto3_clients):
    manager = AWSSessionManager()
    manager.session = MockSession()
    manager.session.factory = mock_boto3_clients['factory']

    def get_session():
        return manager.session

    def get_client(service_name, **kwargs):
        return mock_boto3_clients['factory'](service_name, **kwargs)

    monkeypatch.setattr(manager, 'get_session', get_session)
    monkeypatch.setattr(manager, 'get_client', get_client)
    monkeypatch.setattr(manager, '_is_session_valid', lambda: True)
    monkeypatch.setattr(manager, 'get_available_regions', lambda service_name='ec2': ['us-east-1'])
    return manager


@pytest.fixture
def finops_analyzer(mock_session_manager):
    return FinOpsAnalyzer(session_manager=mock_session_manager)
