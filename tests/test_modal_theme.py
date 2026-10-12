"""Regression: standalone Qt dialogs must share global dark/light colors."""
from unittest.mock import patch

from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QLabel,
                             QMessageBox, QInputDialog, QPushButton)

from app.main_window import MainWindow
from app.settings import Settings
from app.storage import Storage


def test_dark_theme_applied_to_independent_dialogs(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main_window.Settings", lambda: Settings(tmp_path))
    monkeypatch.setattr("app.main_window.Storage", lambda path: Storage(tmp_path / "db"))
    app = QApplication.instance() or QApplication([])
    old_style = app.styleSheet()
    old_palette = QPalette(app.palette())
    window = MainWindow()
    try:
        index = window.theme_selector.findData("dark")
        window.theme_selector.setCurrentIndex(index)
        assert "QDialog QLabel" in app.styleSheet()
        assert "QDialogButtonBox QPushButton" in app.styleSheet()
        dialog = QDialog()
        label = QLabel("로그인 정보", dialog)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dialog)
        dialog.ensurePolished()
        label.ensurePolished()
        button_box.ensurePolished()
        palette = app.palette()
        assert palette.color(QPalette.ColorRole.WindowText).lightness() > palette.color(QPalette.ColorRole.Window).lightness()
        index = window.theme_selector.findData("light")
        window.theme_selector.setCurrentIndex(index)
        assert "QDialog QLabel" in app.styleSheet()
        index = window.theme_selector.findData("system")
        window.theme_selector.setCurrentIndex(index)
        assert app.styleSheet() == ""
    finally:
        window.close()
        app.setPalette(old_palette)
        app.setStyleSheet(old_style)
