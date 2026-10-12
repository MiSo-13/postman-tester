"""Project deletion must be confirmed and isolated to the selected project."""
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QInputDialog

from app.main_window import MainWindow
from app.settings import Settings
from app.storage import Storage


def test_storage_delete_cascades_only_selected_project(tmp_path):
    storage = Storage(tmp_path)
    first = storage.create_project("first")
    second = storage.create_project("second")
    storage.save_project_base_url(first, "http://localhost:8080")
    storage.save_project_base_url(second, "http://localhost:9090")
    storage.save_import(first, "collection", "first.json", {"item": []})
    storage.save_import(second, "collection", "second.json", {"item": []})
    first_run = storage.create_run(first, "run-one")
    second_run = storage.create_run(second, "run-two")
    storage.add_result(first_run, "A", "GET", "/a", "PASS")
    storage.add_result(second_run, "B", "GET", "/b", "PASS")
    storage.save_report(first_run, "html", tmp_path / "first.html")
    storage.save_report(second_run, "html", tmp_path / "second.html")
    assert storage.delete_project(first) == [first_run]
    assert [p["id"] for p in storage.projects()] == [second]
    assert storage.get_project_base_url(second) == "http://localhost:9090"
    assert storage.get_run(first_run) is None
    assert storage.results(second_run)[0]["endpoint_name"] == "B"
    assert storage.reports(second_run)[0]["format"] == "html"
    assert storage.latest_import(second, "collection") is not None


def test_gui_requires_exact_name_and_removes_only_managed_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda root: Storage(tmp_path / "data"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        first = window.storage.create_project("delete-me")
        second = window.storage.create_project("keep-me")
        run_id = window.storage.create_run(first, "one")
        owned_folder = tmp_path / "data" / "reports" / run_id
        owned_folder.mkdir(parents=True)
        (owned_folder / "report.html").write_text("owned")
        other_folder = tmp_path / "data" / "reports" / "unrelated"
        other_folder.mkdir()
        (other_folder / "report.html").write_text("keep")
        window.refresh_projects()
        window.projects.setCurrentIndex(window.projects.findData(first))
        with patch.object(QInputDialog, "getText", return_value=("wrong", True)):
            window.delete_project()
        assert window.storage.get_run(run_id) is not None
        with patch.object(QInputDialog, "getText", return_value=("delete-me", True)):
            window.delete_project()
        assert window.storage.get_run(run_id) is None
        assert not owned_folder.exists()
        assert other_folder.exists()
        assert window.current_project() == second
    finally:
        window.close()
