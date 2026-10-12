"""Regression tests for project-less Qt startup and X11 recovery flag."""
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QPushButton

from app.settings import Settings
from app.storage import Storage
from app.main_window import MainWindow
from main import configure_qt_platform


def test_no_project_disables_actions_without_closing_main_window(tmp_path, monkeypatch):
    # Use isolated SQLite/settings: this test must not depend on the developer's projects.
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda path: Storage(tmp_path / "data"))
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(True)
    window = MainWindow()
    try:
        window.show()
        app.processEvents()
        assert window.isVisible()
        assert not window.current_project()
        buttons = {b.text(): b for b in window.findChildren(QPushButton)}
        for label in ("로그인 설정", "응답 검증 규칙", "응답 변수 추출",
                      "Collection Import", "Environment Import", "AI 테스트 계획"):
            assert not buttons[label].isEnabled(), label
        assert buttons["새 프로젝트"].isEnabled()
        assert window.isVisible()
    finally:
        window.close()


def test_explicit_x11_option_selected_before_qt_import(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    args = ["main.py", "--x11"]
    configure_qt_platform(args)
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"
    assert args == ["main.py"]


def test_linux_defaults_to_xcb(monkeypatch):
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    configure_qt_platform(["main.py"], platform="linux")
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"


def test_linux_keeps_explicit_wayland(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    configure_qt_platform(["main.py"], platform="linux")
    assert os.environ["QT_QPA_PLATFORM"] == "wayland"


def test_windows_and_macos_keep_native_default(monkeypatch):
    for platform in ("win32", "darwin"):
        monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
        configure_qt_platform(["main.py"], platform=platform)
        assert "QT_QPA_PLATFORM" not in os.environ


def test_explicit_x11_flag_overrides_wayland(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")
    argv = ["main.py", "--x11"]
    configure_qt_platform(argv, platform="linux")
    assert os.environ["QT_QPA_PLATFORM"] == "xcb"
    assert argv == ["main.py"]
