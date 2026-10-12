"""App-wide theme palette and persistent selection."""
import pytest
from PyQt6.QtGui import QColor, QPalette

from app.settings import Settings
from app.themes import THEMES, apply_theme, palette_for_theme, validate_theme


def test_supported_themes_and_invalid_values():
    assert THEMES == ("system", "light", "dark")
    for value in THEMES:
        assert validate_theme(value) == value
    for value in ("unknown", "", None, 0):
        with pytest.raises(ValueError):
            validate_theme(value)


def test_palettes_contrast_and_restore_original():
    original = QPalette()
    original.setColor(QPalette.ColorRole.Window, QColor("#123456"))
    system = palette_for_theme("system", original)
    assert system.color(QPalette.ColorRole.Window).name() == "#123456"
    light = palette_for_theme("light", original)
    dark = palette_for_theme("dark", original)
    assert light.color(QPalette.ColorRole.Window) != dark.color(QPalette.ColorRole.Window)
    assert light.color(QPalette.ColorRole.Text) != dark.color(QPalette.ColorRole.Text)
    assert system.color(QPalette.ColorRole.Window) == original.color(QPalette.ColorRole.Window)


def test_settings_theme_survives_restart(tmp_path):
    current = Settings(tmp_path)
    assert current.values["theme"] == "system"
    current.set("theme", "dark")
    assert Settings(tmp_path).values["theme"] == "dark"
    current.set("theme", "light")
    assert Settings(tmp_path).values["theme"] == "light"


def test_apply_theme_on_qt_application():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    original = QPalette(app.palette())
    try:
        apply_theme(app, "dark", original)
        assert app.palette().color(QPalette.ColorRole.Base).name() == "#1e1e1e"
        apply_theme(app, "system", original)
        assert app.palette().color(QPalette.ColorRole.Window) == original.color(
            QPalette.ColorRole.Window)
    finally:
        app.setPalette(original)
