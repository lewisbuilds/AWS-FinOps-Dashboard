"""AWS FinOps Dashboard Package

A comprehensive AWS cost monitoring and tag compliance dashboard.
"""

__version__ = "0.1.0"
__author__ = "AWS FinOps Team"
__email__ = "finops@company.com"

from .finops import FinOpsAnalyzer
from .aws_session import AWSSessionManager
from .logging_config import setup_logging  # noqa: E402

# Initialize logging unless explicitly disabled (e.g., certain test contexts)
import os as _os  # local import to avoid polluting namespace
if _os.getenv("FINOPS_INIT_LOGGING", "true").lower() == "true":  # pragma: no cover
	setup_logging()

__all__ = ['FinOpsAnalyzer', 'AWSSessionManager']
