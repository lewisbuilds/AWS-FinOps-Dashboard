"""AWS Organizations multi-account utilities.

Provides functions to enumerate organization accounts and assume a
read-only role in each member account for cross-account cost analysis
and tag compliance reporting.

Design goals:
 - Reuse existing AWSSessionManager resilience (invoke pattern)
 - Cache account list for configurable TTL (org_cache_ttl)
 - Allow explicit allowlist / exclude list filtering
 - Gracefully skip suspended / closed / inaccessible accounts
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Iterator
import boto3
from botocore.exceptions import ClientError

from .config import get_settings
from .aws_session import AWSSessionManager

logger = logging.getLogger(__name__)


class OrganizationAccountCache:
    """In-memory cache for organization account listing."""

    def __init__(self):
        self._cached: Optional[List[Dict[str, str]]] = None
        self._expiry: Optional[datetime] = None

    def get(self) -> Optional[List[Dict[str, str]]]:
        if self._cached and self._expiry and datetime.utcnow() < self._expiry:
            return self._cached
        return None

    def set(self, accounts: List[Dict[str, str]], ttl_seconds: int):
        self._cached = accounts
        self._expiry = datetime.utcnow() + timedelta(seconds=ttl_seconds)


_account_cache = OrganizationAccountCache()


def list_org_accounts(session_manager: AWSSessionManager) -> List[Dict[str, str]]:
    """List active AWS Organization accounts applying allow/exclude filters.

    Returns list of dicts: { 'id': account_id, 'name': name, 'email': email }.
    """
    settings = get_settings()
    # Single-account mode short-circuit: derive current caller identity only.
    if getattr(settings, "single_account_mode", False):
        try:
            sess = session_manager.get_session()
            sts = sess.client("sts", config=session_manager.config)
            ident = sts.get_caller_identity()
            acct_id = ident.get("Account")
            return [{"id": acct_id, "name": "current", "email": None}]
        except Exception:
            return []
    cached = _account_cache.get()
    if cached is not None:
        return cached

    try:
        org_client = session_manager.get_client('organizations')
    except ClientError as e:
        logger.warning("Organizations API not accessible: %s", e)
        return []

    accounts: List[Dict[str, str]] = []
    paginator = org_client.get_paginator('list_accounts')
    for page in paginator.paginate():
        for acct in page.get('Accounts', []):
            if acct.get('Status') != 'ACTIVE':
                continue
            acct_id = acct.get('Id')
            if settings.org_allowlist and acct_id not in settings.org_allowlist:
                continue
            if acct_id in settings.org_exclude:
                continue
            accounts.append({
                'id': acct_id,
                'name': acct.get('Name'),
                'email': acct.get('Email')
            })

    ttl = settings.org_cache_ttl or 1800
    _account_cache.set(accounts, ttl)
    return accounts


def assume_member_role(account_id: str, session_manager: AWSSessionManager) -> Optional[boto3.Session]:
    """Assume the configured member role inside a target account.

    Returns a boto3 Session or None if assumption fails.
    """
    settings = get_settings()
    role_name = settings.org_member_role_name
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        base_session = session_manager.get_session()
        sts = base_session.client('sts', config=session_manager.config)
        resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f"finops-member-{account_id}",
            DurationSeconds=3600
        )
        creds = resp['Credentials']
        return boto3.Session(
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken'],
            region_name=settings.aws_region
        )
    except ClientError as e:
        code = e.response.get('Error', {}).get('Code')
        logger.warning("Failed to assume role in account %s (%s): %s", account_id, role_name, code)
        return None


def iter_account_cost_explorer_sessions(session_manager: AWSSessionManager) -> Iterator[Dict[str, object]]:
    """Yield dictionaries with account metadata and a Cost Explorer client (if accessible)."""
    for acct in list_org_accounts(session_manager):
        # If current session is already in that account (e.g., single account deployment), reuse
        if session_manager.role_arn and acct['id'] in session_manager.role_arn:
            ce_client = session_manager.get_client('ce')
            yield {"account": acct, "client": ce_client}
            continue
        member_session = assume_member_role(acct['id'], session_manager)
        if not member_session:
            continue
        try:
            ce_client = member_session.client('ce', config=session_manager.config)
            yield {"account": acct, "client": ce_client}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("Skipping account %s due to CE client failure: %s", acct['id'], e)
            continue
