"""Integration-level tests of the existing worker with adaptive decision policies."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from app.main_window import RunWorker
from app.retry_policy import RetryPolicy


def endpoint(name):
    return SimpleNamespace(name=name, method="GET", url="http://example.test/" + name,
                           request={"auth": {"type": "noauth"}, "header": []})


class FakeStorage:
    def __init__(self):
        self.results = []
        self.finished = None

    def add_result(self, run_id, name, method, url, **kwargs):
        self.results.append((name, kwargs["status"]))

    def finish_run(self, run_id, status):
        self.finished = status


def make_worker(stop=False, adaptive=True):
    storage = FakeStorage()
    endpoints = [(str(i) * 64, endpoint(n)) for i, n in
                 enumerate(("failed", "second", "third"), 1)]
    settings = SimpleNamespace(values={
        "default_timeout_seconds": 1,
        "verify_ssl": True,
        "dangerous_methods_enabled": False,
        "file_root": "uploads"}, root=__import__("pathlib").Path("."))
    worker = RunWorker(storage, "run", endpoints, {}, settings, {},
                       stop_on_failure=stop, retry_policy=RetryPolicy(0, 0),
                       adaptive_ai={"key": "example", "model": "gpt-5-mini",
                                    "max_calls": 2} if adaptive else None)
    return worker, storage


def fake_execute(ep, *args, **kwargs):
    status = "FAIL" if ep.name == "failed" else "PASS"
    return {"status": status, "http_status": 500 if status == "FAIL" else 200,
            "elapsed_ms": 1, "detail": "sanitized"}


def test_worker_reorders_remaining_approved_steps_after_failure():
    worker, storage = make_worker()
    calls = []
    def choose(key, model, executed, remaining):
        calls.append([name.name for _, name in remaining])
        return {"action": "continue", "next_id": remaining[1][0],
                "reason": "독립 테스트 우선"}, None
    with patch("app.main_window.execute", side_effect=fake_execute), \
         patch("app.main_window.choose_next", side_effect=choose):
        worker.run()
    assert [name for name, _ in storage.results] == ["failed", "third", "second"]
    assert len(calls) == 1
    assert storage.finished == "COMPLETED"


def test_stop_on_failure_does_not_call_ai():
    worker, storage = make_worker(stop=True)
    with patch("app.main_window.execute", side_effect=fake_execute), \
         patch("app.main_window.choose_next") as choose:
        worker.run()
    choose.assert_not_called()
    assert storage.results == [("failed", "FAIL")]
    assert storage.finished == "STOPPED"


def test_ai_stop_decision_prevents_remaining_requests():
    worker, storage = make_worker()
    with patch("app.main_window.execute", side_effect=fake_execute), \
         patch("app.main_window.choose_next", return_value=(
             {"action": "stop", "next_id": "", "reason": "setup failed"}, None)):
        worker.run()
    assert len(storage.results) == 1
    assert storage.finished == "STOPPED"


def test_ai_failure_falls_back_to_original_approved_order():
    worker, storage = make_worker()
    with patch("app.main_window.execute", side_effect=fake_execute), \
         patch("app.main_window.choose_next", side_effect=ValueError("no connection")):
        worker.run()
    assert [name for name, _ in storage.results] == ["failed", "second", "third"]
    assert storage.finished == "COMPLETED"
