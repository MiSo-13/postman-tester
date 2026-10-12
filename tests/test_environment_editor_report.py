"""Regression coverage for editable environment, login failure reporting and empty exports."""
from unittest.mock import patch
from PyQt6.QtWidgets import QApplication
from app.environment_editor import EnvironmentEditor
from app.storage import Storage
from app.reports import export_reports
from app.main_window import RunWorker
from app.retry_policy import RetryPolicy
from types import SimpleNamespace
from app.user_auth import LoginError


def test_environment_dialog_edits_values():
    app = QApplication.instance() or QApplication([])
    dlg = EnvironmentEditor({"baseUrl": "http://localhost:8080", "region": "old"})
    try:
        dlg.table.item(1, 1).setText("new")
        dlg.accept()
        assert dlg.variables["region"] == "new"
        assert dlg.variables["baseUrl"] == "http://localhost:8080"
    finally:
        dlg.close()


def test_empty_html_report_explains_failure(tmp_path):
    storage = Storage(tmp_path)
    project = storage.create_project("sample")
    run_id = storage.create_run(project, "sample")
    storage.finish_run(run_id, "ERROR")
    paths = export_reports(storage, run_id, tmp_path / "reports")
    html = paths[1].read_text(encoding="utf-8")
    assert "실행 상태" in html and "ERROR" in html
    assert "API 실행 결과가 없습니다" in html


def test_failed_login_is_stored_in_results(tmp_path):
    storage = Storage(tmp_path)
    project = storage.create_project("test")
    run_id = storage.create_run(project, "login")
    endpoint = SimpleNamespace(name="profile", method="GET", url="{{baseUrl}}/profile",
        request={"auth": {"type": "bearer", "bearer": [{"key": "token",
                                                       "value": "{{userAccessToken}}"}]}})
    settings = SimpleNamespace(root=tmp_path, values={
        "default_timeout_seconds": 1, "verify_ssl": True,
        "dangerous_methods_enabled": False, "file_root": "uploads"})
    worker = RunWorker(storage, run_id, [("a", endpoint)],
        {"baseUrl": "http://localhost:8080"}, settings, {},
        user_credentials=("user", "pass"), retry_policy=RetryPolicy(0, 0))
    with patch("app.main_window.login_tokens", side_effect=LoginError("로그인 HTTP 401")):
        worker.run()
    assert storage.get_run(run_id)["status"] == "ERROR"
    result = storage.results(run_id)
    assert len(result) == 1
    assert result[0]["endpoint_name"] == "USER 로그인"
    assert "401" in result[0]["detail"]
