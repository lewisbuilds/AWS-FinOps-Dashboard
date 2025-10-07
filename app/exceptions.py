"""Custom exception hierarchy for the AWS FinOps Dashboard.

These exceptions provide clearer intent, enable more granular error
handling in callers/entrypoints, and support structured logging by
exposing a stable 'error_type' attribute.
"""
from __future__ import annotations
from typing import Optional, Dict, Any


class FinOpsError(Exception):
    """Base exception for all FinOps related errors."""

    error_type = "FinOpsError"

    def __init__(self, message: str, *, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"error_type": self.error_type, "message": str(self), "context": self.context}


class ConfigurationError(FinOpsError):
    error_type = "ConfigurationError"


class AWSSessionError(FinOpsError):
    error_type = "AWSSessionError"


class AWSAuthorizationError(FinOpsError):
    error_type = "AWSAuthorizationError"


class AWSRateLimitError(FinOpsError):
    error_type = "AWSRateLimitError"


class CostDataRetrievalError(FinOpsError):
    error_type = "CostDataRetrievalError"


class TagComplianceError(FinOpsError):
    error_type = "TagComplianceError"


class AnomalyDetectionError(FinOpsError):
    error_type = "AnomalyDetectionError"


class RecommendationRetrievalError(FinOpsError):
    error_type = "RecommendationRetrievalError"
