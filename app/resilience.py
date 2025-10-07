"""Resilience utilities: rate limiting, retries with exponential backoff, and circuit breaker.

Designed to be lightweight and dependency-free so it can wrap AWS SDK (boto3) calls.
All parameters are injected via FinOpsSettings to keep behavior configurable.

Key Concepts:
- RateLimiter: token-bucket style allowing up to N requests per second (burst == rate by default).
- ExponentialBackoff: yields sleep durations with jitter capped at a maximum.
- CircuitBreaker: opens after consecutive failures of retriable types, then half-open after a cooldown.

These primitives are composed by the invoke_with_resilience helper.
"""
from __future__ import annotations
import time
import random
import threading
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Type, Any, Tuple
from botocore.exceptions import ClientError, EndpointConnectionError
from .exceptions import AWSRateLimitError


class RateLimiter:
    """Simple thread-safe token bucket style rate limiter.

    Allows up to `rate` acquisitions per second. Tokens refill continuously.
    """
    def __init__(self, rate: int):
        self.rate = max(1, rate)
        self.capacity = float(self.rate)
        self.tokens = self.capacity
        self.lock = threading.Lock()
        self.timestamp = time.monotonic()

    def acquire(self) -> None:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.timestamp
            # refill tokens
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.timestamp = now
            if self.tokens < 1.0:
                # need to wait
                sleep_for = (1.0 - self.tokens) / self.rate
                time.sleep(sleep_for)
                now2 = time.monotonic()
                elapsed2 = now2 - self.timestamp
                self.tokens = min(self.capacity, self.tokens + elapsed2 * self.rate)
                self.timestamp = now2
            self.tokens -= 1.0


def exponential_backoff(base: float, attempt: int, cap: float) -> float:
    """Calculate exponential backoff with decorrelated jitter.

    Uses the 'Full Jitter' strategy: random(0, min(cap, base * 2**attempt))
    """
    exp = base * (2 ** attempt)
    upper = min(cap, exp)
    return random.uniform(0, upper)


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: Optional[float] = None
    half_open: bool = False


class CircuitBreaker:
    """Circuit breaker for repeated transient failures.

    - Closed: normal operations.
    - Open: fail fast until reset timeout expires.
    - Half-open: allow one trial call; if success -> close, else reopen.
    """
    def __init__(self, fail_threshold: int, reset_seconds: int):
        self.fail_threshold = max(1, fail_threshold)
        self.reset_seconds = max(1, reset_seconds)
        self._state = CircuitState()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._state.opened_at is None:
                return True  # closed
            # open - check if we can transition to half-open
            elapsed = time.monotonic() - self._state.opened_at
            if elapsed >= self.reset_seconds:
                # move to half-open (single trial)
                self._state.half_open = True
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState()  # reset completely

    def record_failure(self) -> None:
        with self._lock:
            if self._state.half_open:
                # immediate reopen
                self._state = CircuitState(failures=self.fail_threshold, opened_at=time.monotonic(), half_open=False)
                return
            self._state.failures += 1
            if self._state.failures >= self.fail_threshold and self._state.opened_at is None:
                self._state.opened_at = time.monotonic()

    def state(self) -> Tuple[str, int]:
        with self._lock:
            if self._state.opened_at is None:
                return ("closed", self._state.failures)
            if self._state.half_open:
                return ("half-open", self._state.failures)
            return ("open", self._state.failures)


TRANSIENT_ERROR_CODES = {
    "Throttling", "ThrottlingException", "RequestLimitExceeded", "TooManyRequestsException",
    "RequestTimeout", "RequestTimeoutException", "InternalError", "InternalServerError",
    "ServiceUnavailable", "Unavailable"
}


def is_transient_error(error: Exception) -> bool:
    if isinstance(error, EndpointConnectionError):
        return True
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        return code in TRANSIENT_ERROR_CODES
    return False


def invoke_with_resilience(
    func: Callable[[], Any],
    rate_limiter: RateLimiter,
    circuit: CircuitBreaker,
    *,
    max_retries: int,
    backoff_base: float,
    backoff_max: float,
    logger,
    context: Optional[dict] = None,
) -> Any:
    """Invoke a callable with rate limiting, retries, and circuit breaker.

    Raises AWSRateLimitError if circuit is open or rate limited beyond retries.
    """
    context = context or {}
    attempt = 0

    while True:
        # Circuit breaker check
        if not circuit.allow():
            state, failures = circuit.state()
            logger.warning(
                "Circuit breaker open - failing fast",
                extra={"error_type": "CircuitOpen", "context": {**context, "state": state, "failures": failures}},
            )
            raise AWSRateLimitError("Circuit breaker open", context={"state": state, "failures": failures})

        # Rate limiting
        try:
            rate_limiter.acquire()
        except Exception:
            # Shouldn't happen, but safety
            time.sleep(0.01)

        try:
            result = func()
            circuit.record_success()
            return result
        except Exception as e:  # noqa: BLE001
            transient = is_transient_error(e)
            if not transient or attempt >= max_retries:
                circuit.record_failure()
                raise
            # transient and we can retry
            sleep_for = exponential_backoff(backoff_base, attempt, backoff_max)
            logger.info(
                "Retrying transient AWS error",
                extra={
                    "error_type": "TransientAWS", "context": {**context, "attempt": attempt + 1, "sleep": round(sleep_for, 3)}
                },
            )
            time.sleep(sleep_for)
            attempt += 1