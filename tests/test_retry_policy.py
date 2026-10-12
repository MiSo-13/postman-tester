"""Safe retry rules and deterministic benchmark-style load regressions."""
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest

from app.retry_policy import RetryPolicy, execute_with_retries
from app.runner import execute


def endpoint(method="GET"):
    return SimpleNamespace(method=method, name="api", url="https://example.test/api", request={"header": []})


def result(status="FAIL", code=503):
    return {"status": status, "http_status": code, "elapsed_ms": 1, "detail": ""}


def test_transient_retry_succeeds_after_two_attempts():
    responses = iter([result(), result("PASS", 200)])
    seen = []
    answer = execute_with_retries(lambda: (seen.append(1), next(responses))[1],
                                  endpoint(), RetryPolicy(2, 0))
    assert answer["status"] == "PASS"
    assert len(seen) == 2


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_never_retries_writes(method):
    count = []
    answer = execute_with_retries(lambda: (count.append(1), result())[1],
                                  endpoint(method), RetryPolicy(5))
    assert answer["status"] == "FAIL"
    assert len(count) == 1


@pytest.mark.parametrize("http_code", [400, 401, 403, 404, 422])
def test_no_retry_for_permanent_http_failures(http_code):
    calls = []
    execute_with_retries(lambda: (calls.append(1), result(code=http_code))[1],
                         endpoint(), RetryPolicy(3))
    assert len(calls) == 1


def test_cancel_during_backoff_prevents_retry():
    calls = []
    cancelled = {"value": False}
    def clock_sleep(seconds):
        cancelled["value"] = True
    answer = execute_with_retries(lambda: (calls.append(1), result())[1],
                                  endpoint(), RetryPolicy(3, 1),
                                  cancelled=lambda: cancelled["value"], sleep=clock_sleep)
    assert answer["http_status"] == 503
    assert len(calls) == 1


def test_cancel_before_attempt_skips_transport():
    called = []
    assert execute_with_retries(lambda: called.append(True), endpoint(),
                                RetryPolicy(3), cancelled=lambda: True) is None
    assert called == []


@pytest.mark.parametrize("count,delay", [(6, 0), (-1, 0), (1, -1), (1, 11), (True, 0)])
def test_invalid_policy(count, delay):
    with pytest.raises(ValueError):
        RetryPolicy(count, delay)


def test_large_mock_collection_reuses_client_without_http_network():
    requests = []
    with httpx.Client(transport=httpx.MockTransport(
            lambda req: (requests.append(req.url.path), httpx.Response(200))[1])) as client:
        for n in range(300):
            api = SimpleNamespace(method="GET", name=f"request {n}",
                                  url=f"https://example.test/{n}", request={"header": []})
            assert execute(api, {}, client=client)["status"] == "PASS"
    assert len(requests) == 300
    assert requests[0] == "/0" and requests[-1] == "/299"
