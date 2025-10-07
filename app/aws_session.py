"""AWS Session Management for FinOps Dashboard

Provides secure session management for AWS services using role assumption or
static credentials, now centralized via FinOpsSettings (Pydantic) for
validated configuration.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
import configparser
import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config
from .config import get_settings
from .exceptions import (
    AWSSessionError,
    AWSAuthorizationError,
    AWSRateLimitError,
)


class AWSSessionManager:
    """Manages AWS sessions with OIDC authentication and credential caching."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.session = None
        self.credentials_cache = {}
        self.cache_expiry = None
        self.settings = get_settings()
        # Guard to avoid repeating profile existence warnings every call
        self._profile_validated = False
        # Resilience primitives (lazy init for thread safety simplicity)
        from .resilience import RateLimiter, CircuitBreaker  # local import to avoid cycles
        self._rate_limiter = RateLimiter(self.settings.rate_limit_rps)
        self._circuit = CircuitBreaker(
            fail_threshold=self.settings.circuit_fail_threshold,
            reset_seconds=self.settings.circuit_reset_seconds,
        )

        # AWS Configuration from validated settings
        self.region = self.settings.aws_region
        self.role_arn = self.settings.assume_role_arn
        self.session_name = f"finops-dashboard-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        # Configure boto3 with retries and timeouts
        self.config = Config(
            retries={'max_attempts': 3, 'mode': 'adaptive'},
            max_pool_connections=50,
            read_timeout=60,
            connect_timeout=10
        )
    
    def get_session(self) -> boto3.Session:
        """Get or create an AWS session with proper authentication.
        
        Returns:
            boto3.Session: Configured AWS session
            
        Raises:
            NoCredentialsError: If AWS credentials cannot be found
            ClientError: If AWS authentication fails
        """
        if self._is_session_valid():
            return self.session
            
        try:
            if self.role_arn:
                # Pre-flight guard: ensure base credentials exist to perform STS AssumeRole
                base = boto3.Session(profile_name=self.settings.aws_profile) if self.settings.aws_profile else boto3.Session()
                # Some test doubles may not implement get_credentials; handle gracefully
                base_creds = None
                try:
                    if hasattr(base, 'get_credentials'):
                        base_creds = base.get_credentials()
                except Exception as _cred_err:  # pragma: no cover - defensive
                    self.logger.debug(f"Credential pre-flight probe failed (ignored in fallback path): {_cred_err}")
                if base_creds is None and not (self.settings.aws_access_key_id and self.settings.aws_secret_access_key):
                    # Provide actionable guidance before we even call STS.
                    hint = (
                        "Cannot assume role because no base credentials were found. "
                        "Remediation options: (a) run 'aws sso login' and set AWS_PROFILE; "
                        "(b) export AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (dev only); "
                        "(c) run on an environment with an instance/container role; or (d) unset AWS_ROLE_ARN."
                    )
                    self.logger.error("AssumeRole pre-flight failed: no base credentials")
                    raise AWSSessionError(
                        "No base credentials available to assume role",
                        context={
                            "role_arn": self.role_arn,
                            "remediation": hint,
                        },
                    )
                self.logger.info(f"Assuming role: {self.role_arn}")
                self.session = self._assume_role_session()
            else:
                if self.settings.aws_access_key_id and self.settings.aws_secret_access_key:
                    self.logger.info("Using static AWS credentials from settings")
                    self.session = boto3.Session(
                        aws_access_key_id=self.settings.aws_access_key_id,
                        aws_secret_access_key=self.settings.aws_secret_access_key,
                        aws_session_token=self.settings.aws_session_token,
                        region_name=self.region,
                    )
                else:
                    if self.settings.aws_profile:
                        # One‑time profile existence diagnostics (developer UX improvement)
                        if not self._profile_validated:
                            self._profile_validated = True
                            try:
                                creds_path = Path("~/.aws/credentials").expanduser()
                                if not creds_path.exists():
                                    self.logger.warning(
                                        "AWS profile '%s' specified but credentials file not found at %s. If running in a container or remote environment, ensure your AWS credentials are accessible (e.g., by mounting your ~/.aws directory or configuring environment variables). Falling back to provider chain if resolution fails.",
                                        self.settings.aws_profile,
                                        creds_path,
                                    )
                                else:
                                    parser = configparser.RawConfigParser()
                                    parser.read(creds_path)
                                    if self.settings.aws_profile not in parser.sections():
                                        self.logger.warning(
                                            "AWS profile '%s' not found in %s (available sections: %s). Check the profile name or mount path.",
                                            self.settings.aws_profile,
                                            creds_path,
                                            parser.sections(),
                                        )
                            except Exception as warn_err:  # pragma: no cover - defensive
                                self.logger.debug(f"Profile diagnostics failed (non-fatal): {warn_err}")
                        self.logger.info(f"Using AWS profile '{self.settings.aws_profile}'")
                        self.session = boto3.Session(profile_name=self.settings.aws_profile, region_name=self.region)
                    else:
                        self.logger.info("Using default AWS credential provider chain")
                        self.session = boto3.Session(region_name=self.region)
                
            # Validate session by making a simple API call
            sts_client = self.session.client('sts', config=self.config)
            identity = sts_client.get_caller_identity()
            self.logger.info(f"AWS session established for: {identity.get('Arn')}")
            
            return self.session
            
        except NoCredentialsError as e:
            self.logger.error(
                "Missing AWS credentials", extra={"error_type": "NoCredentials", "context": {"region": self.region}}
            )
            raise AWSSessionError("AWS credentials not found", context={"region": self.region}) from e
        except ClientError as e:
            code = getattr(e, 'response', {}).get('Error', {}).get('Code')
            if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
                self.logger.warning(
                    "Authorization failure while establishing session", extra={"error_type": code, "context": {"role_arn": self.role_arn}}
                )
                raise AWSAuthorizationError("Authorization failed", context={"role_arn": self.role_arn, "code": code}) from e
            if code in {"Throttling", "ThrottlingException"}:
                self.logger.warning(
                    "Throttled while establishing session", extra={"error_type": code, "context": {"role_arn": self.role_arn}}
                )
                raise AWSRateLimitError("Rate limited by AWS STS", context={"code": code}) from e
            self.logger.error(
                "AWS authentication failed", extra={"error_type": "ClientError", "context": {"code": code}}
            )
            raise AWSSessionError("AWS authentication failed", context={"code": code}) from e
    
    def _assume_role_session(self) -> boto3.Session:
        """Create session using role assumption for OIDC authentication.
        
        Returns:
            boto3.Session: Session with assumed role credentials
        """
        # Create temporary session for STS
        temp_session = boto3.Session(region_name=self.region)
        if temp_session.get_credentials() is None:
            # Double‑check here (should have been caught earlier) for defense in depth.
            raise AWSSessionError(
                "Attempted to assume role without base credentials present",
                context={"role_arn": self.role_arn},
            )
        sts_client = temp_session.client('sts', config=self.config)
        
        # Assume role
        response = sts_client.assume_role(
            RoleArn=self.role_arn,
            RoleSessionName=self.session_name,
            DurationSeconds=3600  # 1 hour
        )
        
        credentials = response['Credentials']
        self.cache_expiry = credentials['Expiration']
        
        # Create session with temporary credentials
        return boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken'],
            region_name=self.region
        )

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def diagnose_credentials(self) -> Dict[str, Any]:
        """Return a diagnostic snapshot of credential discovery state.

        Useful for surfacing to a UI/CLI to help users resolve auth issues.
        """
        base = boto3.Session()
        base_creds = base.get_credentials()
        has_static = bool(self.settings.aws_access_key_id and self.settings.aws_secret_access_key)
        strategy = None
        if self.role_arn:
            strategy = "assume_role"
        elif has_static:
            strategy = "static_keys"
        elif base_creds:
            strategy = "default_chain"
        else:
            strategy = "none"

        remediation: list[str] = []
        if strategy == "assume_role" and not (base_creds or has_static):
            remediation.append("Run 'aws sso login' and set AWS_PROFILE or provide temporary/static keys")
        if strategy == "none":
            remediation.append(
                "Configure credentials: 'aws sso login', or export AWS_ACCESS_KEY_ID/SECRET, or set AWS_ROLE_ARN with base auth."
            )

        return {
            "role_arn": self.role_arn,
            "base_chain_has_credentials": bool(base_creds),
            "has_static_keys": has_static,
            "auth_strategy": strategy,
            "remediation": remediation,
        }
    
    def _is_session_valid(self) -> bool:
        """Check if current session is still valid.
        
        Returns:
            bool: True if session is valid, False otherwise
        """
        if not self.session:
            return False
            
        if self.cache_expiry:
            # Check if credentials are expired (with 5-minute buffer)
            buffer_time = datetime.now() + timedelta(minutes=5)
            if self.cache_expiry <= buffer_time:
                self.logger.info("AWS credentials expiring soon, refreshing session")
                return False
                
        return True
    
    def get_client(self, service_name: str, **kwargs) -> Any:
        """Get AWS service client with current session.
        
        Args:
            service_name: AWS service name (e.g., 'ce', 's3', 'ec2')
            **kwargs: Additional client configuration
            
        Returns:
            AWS service client
        """
        session = self.get_session()
        client_config = {**kwargs}
        if 'config' not in client_config:
            client_config['config'] = self.config
            
        return session.client(service_name, **client_config)
    
    def get_available_regions(self, service_name: str = 'ec2') -> list:
        """Get list of available AWS regions for a service.
        
        Args:
            service_name: AWS service name to check regions for
            
        Returns:
            list: Available region names
        """
        try:
            session = self.get_session()
            return session.get_available_regions(service_name)
        except Exception as e:
            self.logger.error(f"Failed to get available regions: {e}")
            return [self.region]  # Return default region as fallback
    
    def validate_permissions(self) -> Dict[str, bool]:
        """Validate required AWS permissions for FinOps operations.
        
        Returns:
            dict: Permission validation results
        """
        permissions = {
            'cost_explorer': False,
            'organizations': False,
            'support': False,
            'resource_groups': False
        }
        
        try:
            # Test Cost Explorer access
            ce_client = self.get_client('ce')
            ce_client.get_cost_and_usage(
                TimePeriod={
                    'Start': '2023-01-01',
                    'End': '2023-01-02'
                },
                Granularity='DAILY',
                Metrics=['BlendedCost']
            )
            permissions['cost_explorer'] = True
        except ClientError:
            pass
            
        try:
            # Test Organizations access
            org_client = self.get_client('organizations')
            org_client.describe_organization()
            permissions['organizations'] = True
        except ClientError:
            pass
            
        try:
            # Test Support access (optional probe)
            if getattr(self.settings, 'support_probe_enabled', False):
                support_client = self.get_client('support', region_name='us-east-1')
                support_client.describe_services()
                permissions['support'] = True
        except Exception:
            # Silently ignore if probe disabled or inaccessible
            pass
            
        try:
            # Test Resource Groups access
            rg_client = self.get_client('resource-groups')
            rg_client.list_groups()
            permissions['resource_groups'] = True
        except ClientError:
            pass
            
        return permissions
    
    def invoke(self, service: str, method: str, *, client_kwargs=None, call_kwargs=None, context=None):
        """Invoke an AWS client method with resilience (rate limit, retries, circuit breaker).

        Args:
            service: AWS service name (e.g., 'ce').
            method: Method name on the client (e.g., 'get_cost_and_usage').
            client_kwargs: Optional dict for client creation overrides.
            call_kwargs: Optional dict passed to the method.
            context: Extra context for logging.
        Returns: Result of the AWS API call.
        Raises: Propagates underlying exceptions (domain errors can be wrapped by callers).
        """
        client_kwargs = client_kwargs or {}
        call_kwargs = call_kwargs or {}
        context = context or {}

        def _call():
            client = self.get_client(service, **client_kwargs)
            fn = getattr(client, method)
            return fn(**call_kwargs)

        from .resilience import invoke_with_resilience  # local import
        return invoke_with_resilience(
            _call,
            self._rate_limiter,
            self._circuit,
            max_retries=self.settings.max_retries,
            backoff_base=self.settings.backoff_base,
            backoff_max=self.settings.backoff_max,
            logger=self.logger,
            context={"service": service, "method": method, **context},
        )
