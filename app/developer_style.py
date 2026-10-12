"""Developer-tool themed component styling without changing global Qt palettes."""


def developer_stylesheet(theme):
    dark = theme == "dark"
    if theme == "system":
        return ""  # System theme retains native colors and controls.
    panel = "#202733" if dark else "#f2f5f9"
    surface = "#252e3b" if dark else "#ffffff"
    border = "#3b485b" if dark else "#dce3ec"
    text = "#eaf0f8" if dark else "#172433"
    muted = "#9baabd" if dark else "#66788b"
    hover = "#354256" if dark else "#e7eef8"
    field = "#19212c" if dark else "#ffffff"
    disabled_text = "#8190a3" if dark else "#8995a4"
    selected = "#304c70" if dark else "#dbeaff"
    return f"""
    QWidget#ProjectHeader {{ background: {panel}; border-bottom: 1px solid {border}; }}
    QLabel#Brand {{ font-size: 14px; font-weight: 800; letter-spacing: 1px; color: #4e95eb; }}
    QFrame#NavigationSidebar {{ background: {panel}; border-right: 1px solid {border}; }}
    QLabel#NavGroup {{ color: {muted}; font-size: 10px; font-weight: 700; padding: 6px 7px 2px; }}
    QPushButton#NavAction {{
        background: transparent; color: {text}; text-align: left;
        border: 0; border-radius: 6px; padding: 7px 10px; font-weight: 500;
    }}
    QPushButton#NavAction:hover {{ background: {hover}; }}
    QPushButton#NavAction[active="true"] {{
        background: {hover}; border-left: 3px solid #4e95eb; font-weight: 700;
    }}
    QLabel#PageHeading {{ font-size: 22px; font-weight: 800; color: {text}; }}
    QPushButton#NavAction:disabled {{ color: {muted}; }}
    QWidget#EndpointExplorer {{ background: {surface}; }}
    /* Native Qt styles can retain light tab/header text after a runtime
       palette switch. Explicit widget colors avoid near-white on white. */
    QTabWidget::pane {{ border: 1px solid {border}; background: {field}; }}
    QTabBar::tab {{
        background: {panel}; color: {text}; border: 1px solid {border};
        padding: 7px 12px; min-width: 74px;
    }}
    QTabBar::tab:selected {{ background: {surface}; color: {text}; border-bottom: 2px solid #4e95eb; }}
    QTabBar::tab:hover {{ background: {hover}; }}
    QHeaderView::section {{
        background: {panel}; color: {text}; border: 1px solid {border}; padding: 5px;
    }}
    QComboBox, QLineEdit, QTextEdit, QPlainTextEdit, QTreeWidget,
    QTableWidget, QListWidget {{
        background: {field}; color: {text}; border: 1px solid {border};
        selection-background-color: {selected}; selection-color: {text};
    }}
    QComboBox:disabled, QLineEdit:disabled, QPushButton:disabled {{
        color: {disabled_text};
    }}
    QComboBox QAbstractItemView {{
        background: {surface}; color: {text}; selection-background-color: {selected};
    }}
    QComboBox::drop-down {{ border-left: 1px solid {border}; width: 24px; }}
    QPushButton {{
        color: {text}; background: {surface};
        border: 1px solid {border}; border-radius: 5px; padding: 6px 10px;
    }}
    QPushButton:hover {{ background: {hover}; }}
    QPushButton:disabled {{ color: {disabled_text}; background: {panel}; }}
    QTabBar QToolButton {{
        color: {text}; background: {panel}; border: 1px solid {border};
    }}
    QFrame#MetricCard {{
        background: {surface}; border: 1px solid {border}; border-radius: 9px;
    }}
    QLabel#MetricLabel {{ font-size: 11px; color: {muted}; }}
    QLabel#MetricValue {{ font-size: 23px; font-weight: 800; color: {text}; }}
    QLabel#MetricHint {{ font-size: 10px; color: {muted}; }}
    """
