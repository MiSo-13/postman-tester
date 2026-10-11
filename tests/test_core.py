import json
from pathlib import Path

from app.settings import Settings
from app.storage import Storage
from app.templates import save_examples
from app.postman import parse_collection, parse_environment, endpoints_from_document
from app.runner import execute, substitute
from app.reports import export_reports


def test_settings_and_restart(tmp_path):
    settings = Settings(tmp_path)
    assert (tmp_path / "setting.json").exists()
    settings.set("theme", "dark")
    assert Settings(tmp_path).values["theme"] == "dark"


def test_sample_files_importable(tmp_path):
    collection, environment, settings = save_examples(tmp_path)
    document, endpoints = parse_collection(collection)
    assert len(endpoints) == 2
    assert len(endpoints_from_document(document)) == 2
    assert parse_environment(environment)["baseUrl"] == "http://localhost:8080"
    assert json.loads(settings.read_text())["schema_version"] == 1


def test_storage_runs_and_reports_survive_restart(tmp_path):
    storage = Storage(tmp_path / "data")
    project = storage.create_project("Sample")
    run = storage.create_run(project, "1차 실행")
    storage.add_result(run, "상태 확인", "GET", "http://localhost/health",
                       "PASS", 200, 3.5, "")
    storage.finish_run(run, "COMPLETED")
    files = export_reports(storage, run, tmp_path / "data" / "reports" / run)
    assert all(path.exists() for path in files)
    reopened = Storage(tmp_path / "data")
    assert reopened.runs(project)[0]["id"] == run
    assert reopened.results(run)[0]["status"] == "PASS"
    assert {r["format"] for r in reopened.reports(run)} == {"html", "xlsx"}


def test_run_guard_and_variables():
    class Endpoint:
        method = "DELETE"
        url = "{{baseUrl}}/delete"
        request = {}
    assert execute(Endpoint(), {"baseUrl": "http://localhost"})["status"] == "SKIPPED"
    assert substitute("{{baseUrl}}/test", {"baseUrl": "http://localhost"}) == "http://localhost/test"
