"""Response assertion unit and mocked HTTP tests."""
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest

from app.assertions import evaluate_response, validate_rules
from app.runner import execute
from app.storage import Storage


def api():
    return SimpleNamespace(method="GET", url="https://example.test/items",
                           request={"header": []})


def test_json_path_exists_and_equals():
    response = httpx.Response(200, json={"data": {"id": 42, "active": True}})
    ok, detail = evaluate_response(response, [
        {"type": "status", "expected": 200},
        {"type": "exists", "path": "data.id"},
        {"type": "equals", "path": "data.active", "expected": True},
    ])
    assert ok and "3" in detail


def test_missing_path_fails_without_leaking_response():
    response = httpx.Response(200, json={"secret": "sensitive-value"})
    passed, detail = evaluate_response(response, [{"type": "equals",
        "path": "secret", "expected": "different-secret"}])
    assert not passed
    assert "sensitive-value" not in detail and "different-secret" not in detail


def test_boolean_not_equal_integer():
    assert evaluate_response(httpx.Response(200, json={"value": True}),
        [{"type": "equals", "path": "value", "expected": 1}])[0] is False


def test_status_override_and_http_status():
    real = httpx.Client
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: real(
        transport=httpx.MockTransport(lambda _: httpx.Response(404, json={"reason": "missing"})),
        **kwargs)):
        result = execute(api(), {}, assertions=[{"type": "status", "expected": 404}])
    assert result["status"] == "PASS" and result["http_status"] == 404


def test_json_rule_on_non_json_response_fails():
    assert evaluate_response(httpx.Response(200, text="plain"), [
        {"type": "exists", "path": "data"}])[0] is False


def test_invalid_rules_fail_before_network():
    with patch("app.runner.httpx.Client") as client:
        result = execute(api(), {}, assertions=[{"type": "status", "expected": True}])
    assert result["status"] == "BLOCKED"
    client.assert_not_called()


def test_project_specific_persistence(tmp_path):
    storage = Storage(tmp_path)
    a, b = storage.create_project("A"), storage.create_project("B")
    rules = [{"type": "exists", "path": "data.id"}]
    storage.save_response_assertions(a, "endpoint", rules)
    assert Storage(tmp_path).get_response_assertions(a, "endpoint") == rules
    assert storage.get_response_assertions(b, "endpoint") == []


def test_rule_limit():
    with pytest.raises(ValueError):
        validate_rules([{"type": "status", "expected": 200}] * 21)
