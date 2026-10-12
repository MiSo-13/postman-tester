"""Dark/light theme widget contrast regressions."""
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QComboBox, QPushButton, QTabWidget, QTreeWidget, QWidget

from app.developer_style import developer_stylesheet
from app.themes import apply_theme


def test_widget_styles_cover_dark_mode_contrast():
    dark = developer_stylesheet("dark")
    light = developer_stylesheet("light")
    for selector in ("QTabBar::tab", "QHeaderView::section", "QComboBox",
                     "QPushButton", "QTreeWidget", "QTabBar QToolButton"):
        assert selector in dark
        assert selector in light
    assert "color: #eaf0f8" in dark
    assert "background: #202733" in dark
    assert "background: #f2f5f9" in light
    assert developer_stylesheet("system") == ""


def test_runtime_theme_switch_preserves_visible_widget_styles():
    app = QApplication.instance() or QApplication([])
    original_palette = app.palette()
    original_style = app.styleSheet()
    host = QWidget()
    tabs = QTabWidget(host)
    tabs.addTab(QWidget(), "Request 미리보기")
    tree = QTreeWidget(host)
    tree.setHeaderLabels(["API", "Method"])
    combo = QComboBox(host)
    combo.addItem("프로젝트")
    button = QPushButton("테스트 실행", host)
    try:
        for theme in ("dark", "light", "dark"):
            apply_theme(app, theme, original_palette)
            host.setStyleSheet(developer_stylesheet(theme))
            host.ensurePolished()
            for widget in (tabs, tabs.tabBar(), tree.header(), combo, button):
                widget.ensurePolished()
            palette = app.palette()
            foreground = palette.color(palette.ColorRole.Text)
            background = palette.color(palette.ColorRole.Base)
            assert foreground != background
            assert foreground.lightness() > background.lightness() if theme == "dark" else foreground.lightness() < background.lightness()
    finally:
        host.close()
        app.setPalette(original_palette)
        app.setStyleSheet(original_style)
