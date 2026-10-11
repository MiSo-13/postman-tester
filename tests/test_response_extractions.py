"""Response variables pass between sequential API calls without being persisted."""
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest

from app.runner import execute
from app.extractions import validate_extractions
from app.storage import Storage


def api(url, method="GET"):
    return SimpleNamespace(method=method, url=url, request={"header": []})


def test_create_then_fetch_via_extracted_variable():
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == "/users":
            return httpx.Response(201, json={"data": {"userId": 42}})
        return httpx.Response(200, json={"ok": True})
    real_client = httpx.Client
    variables = {"baseUrl": "https://example.test"}
    rules = [{"name": "userId", "path": "data.userId"}]
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: real_client(
            transport=httpx.MockTransport(handler), **kwargs)):
        result1 = execute(api("{{baseUrl}}/users", "POST"), variables,
                          allow_writes=True, extraction_rules=rules,
                          captured_variables=variables)
        result2 = execute(api("{{baseUrl}}/users/{{userId}}"), variables)
    assert result1["status"] == result2["status"] == "PASS"
    assert variables["userId"] == "42"
    assert requests[-1].url.path == "/users/42"


def test_no_capture_for_failed_assertions():
    real_client = httpx.Client
    variables = {"userId": "old"}
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": {"userId": 20}})), **kwargs)):
        result = execute(api("https://example.test"), variables,
            assertions=[{"type": "status", "expected": 201}],
            extraction_rules=[{"name": "userId", "path": "data.userId"}],
            captured_variables=variables)
    assert result["status"] == "FAIL"
    assert variables["userId"] == "old"


def test_capture_is_atomic_when_one_path_missing():
    real_client = httpx.Client
    variables = {}
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": {"id": "private"}})), **kwargs)):
        result = execute(api("https://example.test"), variables,
            extraction_rules=[{"name": "recordId", "path": "data.id"},
                              {"name": "missing", "path": "data.absent"}],
            captured_variables=variables)
    assert result["status"] == "FAIL"
    assert "private" not in result["detail"]
    assert variables == {}


def test_reject_sensitive_or_invalid_variable_names():
    for name in ("baseUrl", "userAccessToken", "sessionToken", "adminAccessToken", ""):
        with pytest.raises(ValueError):
            validate_extractions([{"name": name, "path": "data.id"}])


def test_rules_are_project_isolated(tmp_path):
    store = Storage(tmp_path)
    one, two = store.create_project("one"), store.create_project("two")
    rule = [{"name": "userId", "path": "data.id"}]
    store.save_response_extractions(one, "key1", rule)
    assert Storage(tmp_path).get_response_extractions(one, "key1") == rule
    assert store.get_response_extractions(two, "key1") == []


def test_new_run_starts_without_previous_response_values():
    variables = {"baseUrl": "https://example.test"}
    assert execute(api("{{baseUrl}}/users/{{userId}}"), variables)["status"] == "BLOCKED"
