"""Scenario ordering, duplicate steps, persistence and stale-key validation."""
import pytest
from types import SimpleNamespace
from app.scenarios import resolve_steps, validate_steps
from app.storage import Storage

A, B, C = ("a" * 64, "b" * 64, "c" * 64)


def test_explicit_order_and_repeat():
    endpoints = [SimpleNamespace(name=x) for x in ("A", "B", "C")]
    ordered = resolve_steps([C, A, C], [A, B, C], endpoints)
    assert [e.name for _, e in ordered] == ["C", "A", "C"]


def test_missing_api_fails_before_execution():
    with pytest.raises(ValueError, match="Collection"):
        resolve_steps([A, C], [A, B], [1, 2])


def test_invalid_and_empty_steps():
    for value in ([], ["bad"], [A] * 201, "text"):
        with pytest.raises(ValueError):
            validate_steps(value)


def test_scenario_storage_per_project_and_reload(tmp_path):
    storage = Storage(tmp_path)
    one, two = storage.create_project("one"), storage.create_project("two")
    key = storage.save_scenario(one, "User lifecycle", [C, A, C])
    reopened = Storage(tmp_path)
    item = reopened.scenarios(one)[0]
    assert item["id"] == key
    assert item["name"] == "User lifecycle"
    assert reopened.scenarios(two) == []
    assert storage.save_scenario(one, "Reordered", [A, B], key) == key
    assert storage.scenarios(one)[0]["name"] == "Reordered"
    with pytest.raises(ValueError):
        storage.save_scenario(two, "Other", [A], key)
    storage.delete_scenario(one, key)
    assert storage.scenarios(one) == []
