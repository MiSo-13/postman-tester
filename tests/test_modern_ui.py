"""Modern UI layout, filtering, action preservation, and dashboard metrics."""
from PyQt6.QtWidgets import QApplication, QTreeWidgetItem, QPushButton

from app.main_window import MainWindow
from app.settings import Settings
from app.storage import Storage
from app.ui_components import EndpointExplorer, NavigationSidebar, ProjectHeader
from app.dashboard_widgets import DashboardMetrics
from app.developer_style import developer_stylesheet


def test_components_and_search_filter():
    app = QApplication.instance() or QApplication([])
    explorer = EndpointExplorer()
    parent = QTreeWidgetItem(["Auth", ""])
    login = QTreeWidgetItem(["POST /login", "POST"])
    profile = QTreeWidgetItem(["GET /profile", "GET"])
    parent.addChild(login)
    parent.addChild(profile)
    explorer.tree.addTopLevelItem(parent)
    explorer.search.setText("profile")
    assert not parent.isHidden()
    assert login.isHidden()
    assert not profile.isHidden()
    explorer.search.clear()
    assert not login.isHidden()
    assert not profile.isHidden()


def test_developer_layout_keeps_original_actions(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda root: Storage(tmp_path / "db"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        assert isinstance(window.header, ProjectHeader)
        assert isinstance(window.sidebar, NavigationSidebar)
        assert isinstance(window.explorer, EndpointExplorer)
        assert window.tree is window.explorer.tree
        assert window.projects is window.header.projects
        for label in ("새 프로젝트", "Collection Import", "Environment Import",
                      "로그인 설정", "응답 검증 규칙", "AI 테스트 계획",
                      "테스트 실행", "실행 결과 대시보드"):
            assert label in window.sidebar.buttons
        assert window.sidebar.buttons["새 프로젝트"].isEnabled()
        assert not window.sidebar.buttons["로그인 설정"].isEnabled()
        assert window.cancel_button.text() == "실행 취소"
    finally:
        window.close()


def test_operational_dashboard_numbers_and_themes():
    app = QApplication.instance() or QApplication([])
    metrics = DashboardMetrics({
        "runs": 3, "executed": 20, "failures": 4, "skipped": 2,
        "failure_rate": 20.0, "avg_ms": 132.7,
    })
    assert len(metrics.cards) == 5
    assert [c.value.text() for c in metrics.cards] == [
        "16", "4", "20.0%", "133 ms", "3"]
    assert "NavigationSidebar" in developer_stylesheet("dark")
    assert "NavigationSidebar" in developer_stylesheet("light")
    assert developer_stylesheet("system") == ""
