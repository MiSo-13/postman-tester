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
    QFrame#MetricCard {{
        background: {surface}; border: 1px solid {border}; border-radius: 9px;
    }}
    QLabel#MetricLabel {{ font-size: 11px; color: {muted}; }}
    QLabel#MetricValue {{ font-size: 23px; font-weight: 800; color: {text}; }}
    QLabel#MetricHint {{ font-size: 10px; color: {muted}; }}
    """
