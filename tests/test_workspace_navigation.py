"""Navigation and empty-project workspace regression checks."""
from PyQt6.QtWidgets import QApplication, QStackedWidget

from app.main_window import MainWindow
from app.settings import Settings
from app.storage import Storage


def test_projectless_startup_home_and_navigation(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda path: Storage(tmp_path / "db"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        assert isinstance(window.workspace_stack, QStackedWidget)
        assert window.workspace_stack.currentWidget() is window.home_page
        assert window.sidebar.buttons["홈"].isEnabled()
        assert not window.sidebar.buttons["API 탐색"].isEnabled()
        assert not window.home_page.collection_button.isEnabled()
        window.show_workspace("history")
        assert window.workspace_stack.currentWidget() is window.home_page
        window.open_api_tab("이전 실행")
        assert window.workspace_tabs.tabText(window.workspace_tabs.currentIndex()) == "이전 실행"
    finally:
        window.close()


def test_project_creation_enables_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda path: Storage(tmp_path / "db"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.storage.create_project("development")
        window.refresh_projects()
        assert window.sidebar.buttons["API 탐색"].isEnabled()
        assert window.home_page.collection_button.isEnabled()
        window.show_workspace("history")
        assert window.workspace_stack.currentWidget() is window.history_page
        window.show_workspace("api")
        assert window.workspace_stack.currentWidget() is window.api_page
    finally:
        window.close()
