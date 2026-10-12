"""Extended response assertions with safe error metadata."""
import httpx
import pytest

from app.assertions import evaluate_response, validate_rules
from app.json_paths import find_path, path_parts


def response(data, status=200):
    return httpx.Response(status, json=data)


def test_nested_array_paths_and_all_new_rules():
    data = {"data": {"users": [{"id": 42, "active": True, "tags": ["a", "b"]}]}}
    rules = [
        {"type": "status", "expected": 200},
        {"type": "exists", "path": "data.users[0].id"},
        {"type": "equals", "path": "data.users[0].id", "expected": 42},
        {"type": "value_type", "path": "data.users", "expected": "array"},
        {"type": "value_type", "path": "data.users[0].active", "expected": "boolean"},
        {"type": "range", "path": "data.users[0].id", "min": 40, "max": 50},
        {"type": "length", "path": "data.users[0].tags", "min": 2, "max": 3},
    ]
    assert evaluate_response(response(data), rules) == (True, "검증 7개 통과")


def test_failure_identifies_rule_and_location_without_response_values():
    actual = {"data": {"users": [{"secret": "private-access-token", "id": 1}]}}
    ok, reason = evaluate_response(response(actual), [
        {"type": "exists", "path": "data.users[0]"},
        {"type": "range", "path": "data.users[0].id", "min": 10},
    ])
    assert not ok
    assert "규칙 2" in reason and "data.users[0].id" in reason
    assert "private-access-token" not in reason and "10" not in reason


def test_missing_array_index_fails_without_exception():
    assert find_path({"a": []}, "a[0].id") == (False, None)
    assert evaluate_response(response({"a": []}), [
        {"type": "exists", "path": "a[0].id"}])[0] is False


def test_strict_type_bool_not_number_and_integer():
    assert evaluate_response(response({"value": True}), [
        {"type": "value_type", "path": "value", "expected": "number"}])[0] is False
    assert evaluate_response(response({"value": True}), [
        {"type": "range", "path": "value", "min": 0}])[0] is False


@pytest.mark.parametrize("path", ["", "data..id", "data[*]", "data[-1]",
                                   "data[000]", "data.__secret", "a["])
def test_rejects_invalid_paths(path):
    with pytest.raises(ValueError):
        path_parts(path)


@pytest.mark.parametrize("rule", [
    {"type": "value_type", "path": "a", "expected": []},
    {"type": "value_type", "path": "a", "expected": "unknown"},
    {"type": "range", "path": "a", "min": True},
    {"type": "range", "path": "a", "min": 10, "max": 1},
    {"type": "length", "path": "a", "min": -1},
    {"type": "length", "path": "a", "min": 1.1},
    {"type": "length", "path": "a"},
])
def test_invalid_new_rule_rejected(rule):
    with pytest.raises(ValueError):
        validate_rules([rule])


def test_existing_status_and_equals_unchanged():
    assert evaluate_response(response({"status": "ok"}, 201), [
        {"type": "status", "expected": 201},
        {"type": "equals", "path": "status", "expected": "ok"}])[0]
