from unittest.mock import MagicMock
from app.aws_session import AWSSessionManager


def test_get_session_assumes_role(monkeypatch):
    manager = AWSSessionManager()
    manager.role_arn = 'arn:aws:iam::123456789012:role/TestRole'

    # Mock sts assume_role flow
    mock_session = MagicMock()
    mock_sts_client = MagicMock()
    mock_sts_client.assume_role.return_value = {
        'Credentials': {
            'AccessKeyId': 'ASIA...',
            'SecretAccessKey': 'secret',
            'SessionToken': 'token',
            'Expiration': manager.cache_expiry or manager.cache_expiry
        }
    }
    mock_sts_client.get_caller_identity.return_value = {'Arn': 'arn:aws:iam::123456789012:user/test'}

    class TempSession:
        def get_credentials(self):
            class Creds:
                access_key = 'AKIAFAKE'
                secret_key = 'secret'
                token = None
                def get_frozen_credentials(self):
                    return self
            return Creds()
        def client(self, service, **kwargs):
            if service == 'sts':
                return mock_sts_client
            return MagicMock()

    class AssumedSession:
        def client(self, service, **kwargs):
            return mock_sts_client

    monkeypatch.setattr('boto3.Session', lambda **kwargs: TempSession())
    monkeypatch.setattr(manager, '_assume_role_session', lambda: AssumedSession())

    session = manager.get_session()
    assert session is not None


def test_get_client_uses_config(monkeypatch):
    manager = AWSSessionManager()
    mock_session = MagicMock()
    mock_client = MagicMock()
    mock_session.client.return_value = mock_client
    monkeypatch.setattr(manager, 'get_session', lambda: mock_session)

    client = manager.get_client('ce')
    assert client == mock_client
    mock_session.client.assert_called_once()


def test_get_available_regions_fallback(monkeypatch):
    manager = AWSSessionManager()
    mock_session = MagicMock()
    mock_session.get_available_regions.side_effect = Exception('error')
    monkeypatch.setattr(manager, 'get_session', lambda: mock_session)

    regions = manager.get_available_regions('ec2')
    assert regions == [manager.region]


def test_validate_permissions_partial(monkeypatch):
    manager = AWSSessionManager()

    ce_client = MagicMock()
    ce_client.get_cost_and_usage.return_value = {}

    org_client = MagicMock()
    org_client.describe_organization.return_value = {}

    rg_client = MagicMock()
    rg_client.list_groups.return_value = {}

    def client_factory(service_name, **kwargs):
        if service_name == 'ce':
            return ce_client
        if service_name == 'organizations':
            return org_client
        if service_name == 'support':
            raise Exception('No support access')
        if service_name == 'resource-groups':
            return rg_client
        return MagicMock()

    monkeypatch.setattr(manager, 'get_client', client_factory)

    results = manager.validate_permissions()
    assert results['cost_explorer'] is True
    assert results['organizations'] is True
    assert results['support'] is False
    assert results['resource_groups'] is True
