"""Execution policies and scenario worker progress, without live HTTP calls."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.scenarios import should_stop


@pytest.mark.parametrize("state,expected", [
    ("PASS", False), ("SKIPPED", False), ("FAIL", True),
    ("BLOCKED", True), ("ERROR", True),
])
def test_stop_policy(state, expected):
    assert should_stop(state, True) is expected
    assert should_stop(state, False) is False


def test_worker_stops_after_failure_and_records_step_order(tmp_path):
    from app.main_window import RunWorker
    from app.settings import Settings
    from app.storage import Storage

    settings = Settings(tmp_path)
    project_store = Storage(tmp_path / "data")
    project = project_store.create_project("scenario")
    run_id = project_store.create_run(project, "stop on fail")
    endpoint = lambda name: SimpleNamespace(
        name=name, method="GET", url="https://example.test/" + name,
        request={"header": []})
    endpoints = [(str(i), endpoint(f"step{i}")) for i in range(3)]
    worker = RunWorker(project_store, run_id, endpoints, {}, settings, {},
                       stop_on_failure=True)
    seen = []
    worker.step_result.connect(lambda i, total, name, status:
                               seen.append((i, total, name, status)))
    with patch("app.main_window.execute", side_effect=[
        {"status": "PASS", "http_status": 200, "elapsed_ms": 1, "detail": ""},
        {"status": "FAIL", "http_status": 500, "elapsed_ms": 1, "detail": "HTTP 500"},
    ]) as execute:
        worker.run()
    assert execute.call_count == 2
    assert [row["status"] for row in project_store.results(run_id)] == ["PASS", "FAIL"]
    assert seen == [(1, 3, "step0", "PASS"), (2, 3, "step1", "FAIL")]
    assert project_store.runs(project)[0]["status"] == "STOPPED"


def test_worker_continues_if_policy_disabled(tmp_path):
    from app.main_window import RunWorker
    from app.settings import Settings
    from app.storage import Storage

    settings = Settings(tmp_path)
    store = Storage(tmp_path / "data")
    project = store.create_project("scenario")
    run_id = store.create_run(project, "continue")
    endpoints = [(str(i), SimpleNamespace(
        name=str(i), method="GET", url="https://example.test",
        request={"header": []})) for i in range(2)]
    worker = RunWorker(store, run_id, endpoints, {}, settings, {},
                       stop_on_failure=False)
    with patch("app.main_window.execute", side_effect=[
        {"status": "FAIL", "http_status": 500, "elapsed_ms": 1, "detail": "HTTP 500"},
        {"status": "PASS", "http_status": 200, "elapsed_ms": 1, "detail": ""},
    ]) as execute:
        worker.run()
    assert execute.call_count == 2
    assert store.runs(project)[0]["status"] == "COMPLETED"
