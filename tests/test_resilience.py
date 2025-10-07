import time
from unittest.mock import MagicMock
import pytest

from app.resilience import RateLimiter, CircuitBreaker, invoke_with_resilience, is_transient_error, TRANSIENT_ERROR_CODES
from botocore.exceptions import ClientError, EndpointConnectionError


class DummyLogger:
    def __init__(self):
        self.records = []
    def info(self, msg, extra=None):
        self.records.append(("info", msg, extra))
    def warning(self, msg, extra=None):
        self.records.append(("warning", msg, extra))


def make_client_error(code: str):
    return ClientError({"Error": {"Code": code, "Message": code}}, operation_name="TestOp")


def test_rate_limiter_basic_throughput():
    rl = RateLimiter(rate=5)
    start = time.monotonic()
    # Acquire 10 tokens; with rate 5/s should take >=1s
    for _ in range(10):
        rl.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 1.0  # ensures limiting actually happened


def test_circuit_breaker_opens_and_resets(monkeypatch):
    cb = CircuitBreaker(fail_threshold=3, reset_seconds=1)
    # trip circuit
    for _ in range(3):
        cb.record_failure()
    state, failures = cb.state()
    assert state == "open"
    assert failures == 3
    # not allowed immediately
    assert not cb.allow()
    # after reset_seconds -> half-open allowed
    time.sleep(1.05)
    assert cb.allow()  # transitions to half-open
    # success closes
    cb.record_success()
    state2, _ = cb.state()
    assert state2 == "closed"


def test_invoke_with_resilience_retries_transient(monkeypatch):
    rl = RateLimiter(100)  # effectively no wait
    cb = CircuitBreaker(fail_threshold=5, reset_seconds=60)
    logger = DummyLogger()
    attempts = {"n": 0}

    def func():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise make_client_error("Throttling")
        return "ok"

    result = invoke_with_resilience(
        func,
        rl,
        cb,
        max_retries=5,
        backoff_base=0.01,
        backoff_max=0.05,
        logger=logger,
        context={"test": "retry"},
    )
    assert result == "ok"
    # Two retries expected
    throttle_logs = [r for r in logger.records if r[0] == "info" and r[2] and r[2].get("error_type") == "TransientAWS"]
    assert len(throttle_logs) == 2


def test_invoke_with_resilience_propagates_non_transient():
    rl = RateLimiter(100)
    cb = CircuitBreaker(fail_threshold=5, reset_seconds=60)
    logger = DummyLogger()

    def func():
        raise make_client_error("ValidationException")

    with pytest.raises(ClientError):
        invoke_with_resilience(
            func,
            rl,
            cb,
            max_retries=2,
            backoff_base=0.01,
            backoff_max=0.05,
            logger=logger,
        )


def test_invoke_with_resilience_circuit_opens():
    rl = RateLimiter(100)
    cb = CircuitBreaker(fail_threshold=2, reset_seconds=60)
    logger = DummyLogger()

    def func():
        raise make_client_error("Throttling")

    # exceed retries to record failures
    with pytest.raises(ClientError):
        invoke_with_resilience(
            func,
            rl,
            cb,
            max_retries=1,
            backoff_base=0.0,
            backoff_max=0.0,
            logger=logger,
        )
    # invoke again causing another failure to reach threshold
    with pytest.raises(ClientError):
        invoke_with_resilience(
            func,
            rl,
            cb,
            max_retries=0,
            backoff_base=0.0,
            backoff_max=0.0,
            logger=logger,
        )
    state, failures = cb.state()
    assert state == "open"


def test_is_transient_error():
    assert is_transient_error(EndpointConnectionError(endpoint_url="https://example.com"))
    for code in TRANSIENT_ERROR_CODES:
        assert is_transient_error(make_client_error(code))
    assert not is_transient_error(make_client_error("ValidationException"))
