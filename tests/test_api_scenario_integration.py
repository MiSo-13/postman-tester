"""End-to-end scenario execution against an in-process HTTP transport.

No production network; real runner, extraction, assertion, persistence, retry
and stop/cancel policies are exercised together.
"""
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.main_window import RunWorker
from app.settings import Settings
from app.storage import Storage
from app.retry_policy import RetryPolicy


def endpoint(name, method, url, *, body=None, auth=None):
    request = {"header": [], "body": body or {}}
    if auth:
        request["auth"] = {"type": "bearer",
                           "bearer": [{"key": "token", "value": "{{userAccessToken}}"}]}
    return SimpleNamespace(name=name, method=method, url=url, request=request)


def setup(tmp_path, label="lifecycle"):
    settings = Settings(tmp_path)
    settings.set("dangerous_methods_enabled", True)
    storage = Storage(tmp_path / "data")
    project = storage.create_project("integration")
    run_id = storage.create_run(project, label)
    return settings, storage, project, run_id


def make_worker(settings, storage, run_id, steps, **kwargs):
    return RunWorker(storage, run_id, [(str(i), item) for i, item in enumerate(steps)],
                     {"baseUrl": "https://example.test"}, settings, {}, **kwargs)


def transport_patch(handler):
    original = httpx.Client
    return patch("app.main_window.httpx.Client", side_effect=lambda **kwargs:
                 original(transport=httpx.MockTransport(handler), **kwargs))


def test_login_create_extract_fetch_assert_and_persist(tmp_path):
    settings, storage, project, run_id = setup(tmp_path)
    calls = []
    def handler(request):
        calls.append((request.method, request.url.path,
                      request.headers.get("authorization")))
        if request.method == "POST" and request.url.path == "/users":
            assert request.headers["authorization"] == "Bearer access-secret"
            return httpx.Response(201, json={"data": {"userId": 42}})
        if request.method == "GET" and request.url.path == "/users/42":
            assert request.headers["authorization"] == "Bearer access-secret"
            return httpx.Response(200, json={"data": {"userId": 42, "active": True}})
        return httpx.Response(404, json={"error": "missing"})

    steps = [endpoint("create", "POST", "{{baseUrl}}/users",
                      body={"mode": "raw", "raw": '{"name":"tester"}'}, auth=True),
             endpoint("fetch", "GET", "{{baseUrl}}/users/{{userId}}", auth=True)]
    worker = make_worker(settings, storage, run_id, steps,
        user_credentials=("user@example.test", "password"),
        extraction_rules={"0": [{"name": "userId", "path": "data.userId"}]},
        response_rules={
            "0": [{"type": "status", "expected": 201}],
            "1": [{"type": "status", "expected": 200},
                  {"type": "equals", "path": "data.userId", "expected": 42},
                  {"type": "equals", "path": "data.active", "expected": True}],
        })
    with transport_patch(handler), patch("app.main_window.login_tokens",
                                        return_value=("access-secret", None)):
        worker.run()
    assert [r["status"] for r in storage.results(run_id)] == ["PASS", "PASS"]
    assert storage.runs(project)[0]["status"] == "COMPLETED"
    assert worker.variables["userId"] == "42"
    assert [x[1] for x in calls] == ["/users", "/users/42"]
    assert "access-secret" not in str(storage.results(run_id))
    assert "password" not in str(storage.results(run_id))


def test_failed_assertion_stops_scenario_and_does_not_capture(tmp_path):
    settings, storage, project, run_id = setup(tmp_path)
    seen = []
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"data": {"id": 123}})
    steps = [endpoint("bad", "GET", "{{baseUrl}}/first"),
             endpoint("not-run", "GET", "{{baseUrl}}/second")]
    worker = make_worker(settings, storage, run_id, steps,
        stop_on_failure=True,
        response_rules={"0": [{"type": "equals", "path": "data.id", "expected": 999}]},
        extraction_rules={"0": [{"name": "savedId", "path": "data.id"}]})
    with transport_patch(handler):
        worker.run()
    assert seen == ["/first"]
    assert [r["status"] for r in storage.results(run_id)] == ["FAIL"]
    assert storage.runs(project)[0]["status"] == "STOPPED"
    assert "savedId" not in worker.variables
    assert "123" not in storage.results(run_id)[0]["detail"]


def test_write_disabled_skips_and_unresolved_reference_blocked(tmp_path):
    settings, storage, project, run_id = setup(tmp_path)
    settings.set("dangerous_methods_enabled", False)
    requests = []
    steps = [endpoint("create", "POST", "{{baseUrl}}/users"),
             endpoint("fetch", "GET", "{{baseUrl}}/users/{{userId}}")]
    worker = make_worker(settings, storage, run_id, steps,
                         stop_on_failure=True)
    with transport_patch(lambda request: (requests.append(request), httpx.Response(200))[1]):
        worker.run()
    assert requests == []
    assert [r["status"] for r in storage.results(run_id)] == ["SKIPPED", "BLOCKED"]
    assert storage.runs(project)[0]["status"] == "STOPPED"


def test_read_retry_and_cancel_without_subsequent_request(tmp_path):
    settings, storage, project, run_id = setup(tmp_path)
    calls = []
    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(503 if len(calls) == 1 else 200)
    worker = make_worker(settings, storage, run_id,
        [endpoint("retry", "GET", "{{baseUrl}}/first"),
         endpoint("next", "GET", "{{baseUrl}}/second")],
        retry_policy=RetryPolicy(2, 0))
    def cancel_after_first_step(i, total, name, status):
        worker.cancel()
    worker.step_result.connect(cancel_after_first_step)
    with transport_patch(handler):
        worker.run()
    rows = storage.results(run_id)
    assert len(rows) == 1 and rows[0]["status"] == "PASS"
    assert rows[0]["retry_count"] == 1
    assert calls == ["/first", "/first"]
    assert storage.runs(project)[0]["status"] == "CANCELLED"
