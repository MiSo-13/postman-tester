"""Opt-in retry policy for transient failures on read-only requests."""
from dataclasses import dataclass
import time

SAFE_METHODS = frozenset(("GET", "HEAD", "OPTIONS"))
TRANSIENT_STATUSES = frozenset((408, 429, 500, 502, 503, 504))


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 0
    delay_seconds: float = 0.0

    def __post_init__(self):
        if type(self.retries) is not int or not 0 <= self.retries <= 5:
            raise ValueError("재시도 횟수는 0~5 사이여야 합니다.")
        if type(self.delay_seconds) not in (int, float) or not 0 <= self.delay_seconds <= 10:
            raise ValueError("재시도 간격은 0~10초 사이여야 합니다.")


def should_retry(method, result, attempt, policy):
    if method.upper() not in SAFE_METHODS or attempt >= policy.retries:
        return False
    return (result["status"] == "ERROR" or
            result["http_status"] in TRANSIENT_STATUSES and
            result["status"] == "FAIL")


def execute_with_retries(execute_one, endpoint, policy, cancelled=lambda: False,
                         sleep=time.sleep):
    """Retry only explicitly transient failures; never retry writes."""
    for attempt in range(policy.retries + 1):
        if cancelled():
            return None
        result = execute_one()
        if not should_retry(endpoint.method, result, attempt, policy):
            return result
        if cancelled():
            return result
        if policy.delay_seconds:
            # Small chunks ensure cancellation can interrupt retry backoff.
            deadline = time.monotonic() + policy.delay_seconds
            while not cancelled():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                sleep(min(0.1, remaining))
        if cancelled():
            return result
    return result
