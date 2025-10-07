from functools import lru_cache
from typing import List, Optional
from decimal import Decimal
import re
import logging
import boto3
from pydantic import Field, field_validator, model_validator, ConfigDict, AliasChoices

# Pydantic v2 moved BaseSettings to pydantic_settings. Provide flexible import so
# tests still run if an older v1 environment is used (though project targets v2).
try:  # pragma: no cover - simple import shim
    from pydantic_settings import BaseSettings  # type: ignore
except ImportError:  # Fallback (unlikely in this project after adding dependency)
    from pydantic import BaseSettings  # type: ignore


class FinOpsSettings(BaseSettings):
    """Centralized configuration with validation for FinOps Dashboard.

    New in this revision:
    - Added report/export & email (SES) related settings.
    - Migrated legacy @validator usages to Pydantic v2 @field_validator to remove deprecation warnings.
    - Retained backwards-compatible semantics for list-like comma separated fields.
    """

    # Accept both AWS_REGION and AWS_DEFAULT_REGION; AWS_REGION takes precedence if both set.
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_REGION", "AWS_DEFAULT_REGION"),
        description="Primary AWS region for API calls"
    )
    assume_role_arn: Optional[str] = Field(default=None, validation_alias="AWS_ROLE_ARN")
    aws_access_key_id: Optional[str] = Field(default=None, validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = Field(default=None, validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: Optional[str] = Field(default=None, validation_alias="AWS_SESSION_TOKEN")
    aws_profile: Optional[str] = Field(default=None, validation_alias="AWS_PROFILE", description="Shared credentials / SSO profile name")

    required_tag_keys: str = Field(default="Environment,Owner,Project,CostCenter", validation_alias="REQUIRED_TAG_KEYS")

    daily_cost_warning: Decimal = Field(default=Decimal("1000.00"), validation_alias="DAILY_COST_WARNING")
    monthly_cost_warning: Decimal = Field(default=Decimal("10000.00"), validation_alias="MONTHLY_COST_WARNING")
    anomaly_threshold: float = Field(default=0.20, validation_alias="ANOMALY_THRESHOLD")

    # Resilience settings
    rate_limit_rps: int = Field(default=5, validation_alias="RATE_LIMIT_RPS", ge=1, le=1000)
    max_retries: int = Field(default=5, validation_alias="MAX_RETRIES", ge=0, le=10)
    backoff_base: float = Field(default=0.3, validation_alias="BACKOFF_BASE", ge=0.0, le=30.0)
    backoff_max: float = Field(default=8.0, validation_alias="BACKOFF_MAX", ge=0.5, le=120.0)
    circuit_fail_threshold: int = Field(default=5, validation_alias="CB_FAIL_THRESHOLD", ge=1, le=50)
    circuit_reset_seconds: int = Field(default=60, validation_alias="CB_RESET_SECONDS", ge=5, le=3600)

    # Caching settings
    cache_backend: str = Field(
        default="memory", validation_alias="CACHE_BACKEND", description="Cache backend: memory or redis"
    )
    cache_default_ttl_seconds: int = Field(
        default=300, validation_alias="CACHE_DEFAULT_TTL_SECONDS", ge=1, le=86400
    )
    cache_max_entries: int = Field(
        default=1000, validation_alias="CACHE_MAX_ENTRIES", ge=10, le=1_000_000
    )
    redis_url: Optional[str] = Field(
        default=None, validation_alias="REDIS_URL", description="Redis connection URL if using redis backend"
    )
    # Specific TTL overrides (seconds) per data domain
    cost_ttl: Optional[int] = Field(default=None, validation_alias="COST_TTL")
    anomaly_ttl: Optional[int] = Field(default=None, validation_alias="ANOMALY_TTL")
    recommendation_ttl: Optional[int] = Field(default=None, validation_alias="RECOMMENDATION_TTL")
    tag_compliance_ttl: Optional[int] = Field(default=None, validation_alias="TAG_COMPLIANCE_TTL")

    # Advanced anomaly detection settings
    anomaly_history_days: int = Field(default=60, validation_alias="ANOMALY_HISTORY_DAYS", ge=7, le=400)
    anomaly_zscore_threshold: float = Field(default=3.0, validation_alias="ANOMALY_ZSCORE_THRESHOLD", ge=0.5, le=10.0)
    anomaly_iforest_contamination: float = Field(default=0.05, validation_alias="ANOMALY_IFOREST_CONTAMINATION", ge=0.001, le=0.5)
    anomaly_method: str = Field(default="both", validation_alias="ANOMALY_METHOD")  # zscore, iforest, both
    anomaly_min_points: int = Field(default=14, validation_alias="ANOMALY_MIN_POINTS", ge=7, le=10000)
    anomaly_alert_enabled: bool = Field(default=True, validation_alias="ANOMALY_ALERT_ENABLED")

    # General UI / runtime convenience settings (previously expected in .env but missing -> caused extra field errors)
    lookback_days: int = Field(
        default=30,
        validation_alias="LOOKBACK_DAYS",
        ge=1,
        le=400,
        description="Default number of days for cost/time‑series lookbacks when not specified explicitly"
    )
    log_level: str = Field(
        default="INFO",
        validation_alias="LOG_LEVEL",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)"
    )
    log_format: str = Field(
        default="text",
        validation_alias="LOG_FORMAT",
        description="Log output format: text or json"
    )

    # AWS Organizations / Multi-account settings
    org_management_account_id: Optional[str] = Field(
        default=None, validation_alias="ORG_MANAGEMENT_ACCOUNT_ID", description="Management (payer) account ID"
    )
    org_member_role_name: str = Field(
        default="OrganizationAccountAccessRole", validation_alias="ORG_MEMBER_ROLE_NAME",
        description="Role name to assume in member accounts for read-only access"
    )
    org_account_allowlist: Optional[str] = Field(
        default=None, validation_alias="ORG_ACCOUNT_ALLOWLIST", description="Comma list of account IDs to include (if set)"
    )
    org_account_exclude_list: Optional[str] = Field(
        default=None, validation_alias="ORG_ACCOUNT_EXCLUDE_LIST", description="Comma list of account IDs to exclude"
    )
    org_cache_ttl: Optional[int] = Field(
        default=1800, validation_alias="ORG_CACHE_TTL", description="TTL (seconds) for cached organization account list"
    )

    # Pydantic v2 config
    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Reporting / export settings
    report_output_dir: str = Field(default="reports", validation_alias="REPORT_OUTPUT_DIR")
    report_default_formats: str = Field(
        default="csv,json,xlsx", validation_alias="REPORT_DEFAULT_FORMATS",
        description="Comma separated list of default export formats (csv,json,xlsx)"
    )
    report_schedule_enabled: bool = Field(default=False, validation_alias="REPORT_SCHEDULE_ENABLED")
    report_schedule_cron: Optional[str] = Field(
        default=None, validation_alias="REPORT_SCHEDULE_CRON",
        description="Cron expression for scheduled report generation (5 fields)"
    )
    report_schedule_timezone: str = Field(
        default="UTC", validation_alias="REPORT_SCHEDULE_TIMEZONE",
        description="Timezone name for scheduler (e.g. UTC, US/Eastern)"
    )
    # Email / SES settings
    ses_enabled: bool = Field(default=False, validation_alias="SES_ENABLED")
    ses_region: Optional[str] = Field(default=None, validation_alias="SES_REGION")
    ses_sender_email: Optional[str] = Field(default=None, validation_alias="SES_SENDER_EMAIL")
    ses_recipient_emails: Optional[str] = Field(
        default=None, validation_alias="SES_RECIPIENT_EMAILS",
        description="Comma separated list of recipient email addresses"
    )
    max_excel_rows: int = Field(
        default=1_000_000, validation_alias="MAX_EXCEL_ROWS", ge=1, le=1_048_576,
        description="Safety cap for rows written to Excel workbooks"
    )
    # Mode / feature toggles
    single_account_mode: bool = Field(
        default=False, validation_alias="SINGLE_ACCOUNT_MODE",
        description="If true, skip AWS Organizations enumeration and treat current account as sole scope"
    )
    support_probe_enabled: bool = Field(
        default=False, validation_alias="SUPPORT_PROBE_ENABLED",
        description="If true, perform Support API permission probe (DescribeServices); off reduces IAM surface"
    )

    @field_validator("aws_region")
    def validate_region(cls, v: str) -> str:
        if not re.match(r"^[a-z]{2}-[a-z]+-\d$", v):
            raise ValueError(f"Invalid AWS region format: {v}")
        try:
            known = boto3.session.Session().get_available_regions("ec2")
            if v not in known:
                raise ValueError(f"AWS region '{v}' not in known region list")
        except Exception:
            pass
        return v

    @field_validator("required_tag_keys")
    def validate_required_tags(cls, v: str) -> str:
        tags = [t.strip() for t in v.split(",") if t.strip()]
        if not tags:
            raise ValueError("At least one required tag key must be specified")
        if any(len(t) > 64 for t in tags):
            raise ValueError("Tag keys must be <= 64 characters")
        return ",".join(tags)

    @field_validator("daily_cost_warning", "monthly_cost_warning")
    def validate_positive_decimal(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Cost thresholds must be positive values")
        return v

    @field_validator("anomaly_threshold")
    def validate_anomaly_threshold(cls, v: float) -> float:
        if v <= 0 or v >= 1:
            raise ValueError("Anomaly threshold must be between 0 and 1 (exclusive)")
        return v

    @field_validator("cache_backend")
    def validate_cache_backend(cls, v: str) -> str:
        allowed = {"memory", "redis"}
        if v not in allowed:
            raise ValueError(f"cache_backend must be one of {allowed}")
        return v

    @field_validator("anomaly_method")
    def validate_anomaly_method(cls, v: str) -> str:
        allowed = {"zscore", "iforest", "both"}
        if v not in allowed:
            raise ValueError(f"anomaly_method must be one of {allowed}")
        return v

    @field_validator("log_level")
    def validate_log_level(cls, v: str) -> str:
        lvl = v.upper().strip()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if lvl not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return lvl

    @field_validator("log_format")
    def validate_log_format(cls, v: str) -> str:
        fmt = v.strip().lower()
        allowed = {"text", "json"}
        if fmt not in allowed:
            raise ValueError(f"log_format must be one of {sorted(allowed)}")
        return fmt

    @field_validator("org_management_account_id", "org_member_role_name", mode="before")
    def strip_strings(cls, v):  # type: ignore
        if v is None:
            return v
        vs = str(v).strip()
        return vs or None

    @field_validator("org_management_account_id")
    def validate_account_id(cls, v):  # type: ignore
        if v is None:
            return v
        if not re.match(r"^\d{12}$", v):
            raise ValueError("Management account ID must be a 12-digit numeric string")
        return v

    @field_validator("org_account_allowlist", "org_account_exclude_list", mode="before")
    def normalize_account_lists(cls, v):  # type: ignore
        if v in (None, ""):
            return None
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        for p in parts:
            if not re.match(r"^\d{12}$", p):
                raise ValueError(f"Invalid AWS account id in list: {p}")
        return ",".join(parts) if parts else None

    @field_validator(
        "cache_default_ttl_seconds",
        "cost_ttl",
        "anomaly_ttl",
        "recommendation_ttl",
        "tag_compliance_ttl",
        mode="before",
    )
    def validate_ttls(cls, v):  # type: ignore
        if v is None or v == "" or v == 0:
            return None
        iv = int(v)
        if iv <= 0:
            raise ValueError("TTL values must be positive integers")
        return iv

    # Report / email specific validators
    @field_validator("report_default_formats")
    def validate_report_formats(cls, v: str) -> str:
        parts = [p.strip().lower() for p in v.split(",") if p.strip()]
        allowed = {"csv", "json", "xlsx"}
        invalid = [p for p in parts if p not in allowed]
        if invalid:
            raise ValueError(f"Unsupported report formats: {invalid}. Allowed: {sorted(allowed)}")
        return ",".join(parts)

    @field_validator("report_schedule_cron")
    def validate_cron(cls, v: Optional[str]):  # type: ignore
        if v is None:
            return v
        # Very lightweight 5-field cron validation (space separated, no newlines)
        if not re.match(r"^(\S+\s+){4}\S+$", v.strip()):
            raise ValueError("report_schedule_cron must be a standard 5-field cron expression")
        return v.strip()

    @field_validator("ses_sender_email")
    def validate_sender_email(cls, v: Optional[str]):  # type: ignore
        if v is None:
            return v
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", v):
            raise ValueError("Invalid ses_sender_email format")
        return v

    @field_validator("ses_recipient_emails", mode="before")
    def normalize_recipient_emails(cls, v: Optional[str]):  # type: ignore
        if v in (None, ""):
            return None
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        for e in parts:
            if not re.match(r"^[^@]+@[^@]+\.[^@]+$", e):
                raise ValueError(f"Invalid recipient email format: {e}")
        return ",".join(parts) if parts else None

    @field_validator("report_output_dir")
    def validate_report_output_dir(cls, v: str) -> str:  # type: ignore
        # Disallow path traversal components. Allow relative or absolute paths without '..'.
        from pathlib import Path
        p = Path(v)
        if any(part == ".." for part in p.parts):
            raise ValueError("report_output_dir must not contain path traversal components ('..')")
        # Optionally enforce single nested depth (soft); skip for absolute.
        return v

    @model_validator(mode="after")
    def validate_auth_method(self):
        # Provide contextual logging about authentication strategy without spamming for valid profile usage.
        logger = logging.getLogger(__name__)
        has_role = bool(self.assume_role_arn)
        has_static = bool(self.aws_access_key_id and self.aws_secret_access_key)
        has_profile = bool(self.aws_profile)
        if has_role:
            # Role assumption path will still rely on base creds (could be profile, env, SSO, etc.)
            logger.debug("Auth strategy: assume_role (role_arn set)")
        elif has_static:
            logger.debug("Auth strategy: static_keys (AWS_ACCESS_KEY_ID / SECRET provided)")
        elif has_profile:
            # Previously this produced a fallback warning; now treat as a first-class explicit strategy.
            logger.debug(f"Auth strategy: profile ('{self.aws_profile}')")
        else:
            logger.warning(
                "No explicit AWS auth provided (no role, profile, or static keys). Falling back to default provider chain (env vars, instance profile, SSO cache)."
            )
        return self

    @model_validator(mode="before")
    @classmethod
    def strip_inline_comments(cls, data):  # type: ignore
        """Sanitize raw environment values before field coercion.

        Many users add inline comments in .env like:
            RATE_LIMIT_RPS=5  # Max AWS API calls
        Pydantic attempts to parse the entire string; this pre-processor removes the inline
        comment portion after a '#' unless the value begins with '#'. Only applies to str values.
        """
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, str):
                    # Split on first '#', keep left part
                    parts = v.split('#', 1)
                    primary = parts[0].strip()
                    cleaned[k] = primary
                else:
                    cleaned[k] = v
            return cleaned
        return data

    @property
    def required_tags_list(self) -> List[str]:
        return [t.strip() for t in self.required_tag_keys.split(",") if t.strip()]

    @property
    def cost_thresholds(self):
        return {
            "daily_warning": self.daily_cost_warning,
            "monthly_warning": self.monthly_cost_warning,
            "anomaly_threshold": self.anomaly_threshold,
        }

    @property
    def report_formats_list(self) -> List[str]:
        return [f for f in self.report_default_formats.split(",") if f]

    @property
    def ses_recipient_list(self) -> Optional[List[str]]:
        return [e for e in (self.ses_recipient_emails or "").split(",") if e] or None

    @property
    def cache_ttls(self) -> dict:
        """Return effective TTLs per domain, falling back to default when not set."""
        default = self.cache_default_ttl_seconds
        return {
            "cost": self.cost_ttl or default,
            "anomaly": self.anomaly_ttl or default,
            "recommendation": self.recommendation_ttl or default,
            "tag_compliance": self.tag_compliance_ttl or default,
        }

    @property
    def org_allowlist(self) -> Optional[list]:
        return [a for a in (self.org_account_allowlist or "").split(",") if a] or None

    @property
    def org_exclude(self) -> set:
        return set([a for a in (self.org_account_exclude_list or "").split(",") if a])


@lru_cache()
def get_settings() -> FinOpsSettings:
    return FinOpsSettings()
