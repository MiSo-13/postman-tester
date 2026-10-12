"""Application-wide light/dark/system palette selection for PyQt6."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

THEMES = ("system", "light", "dark")


def validate_theme(theme: str) -> str:
    if theme not in THEMES or not isinstance(theme, str):
        raise ValueError("테마는 system, light, dark 중 하나여야 합니다.")
    return theme


def palette_for_theme(theme: str, system_palette: QPalette) -> QPalette:
    validate_theme(theme)
    if theme == "system":
        return QPalette(system_palette)
    palette = QPalette(system_palette)
    dark = theme == "dark"
    background = "#1e1e1e" if dark else "#ffffff"
    window = "#252525" if dark else "#f6f7f9"
    foreground = "#f4f4f4" if dark else "#202124"
    alternate = "#303030" if dark else "#edf1f5"
    highlight = "#427ac8" if dark else "#2468b5"
    disabled = "#878787" if dark else "#888888"
    for role, color in (
        (QPalette.ColorRole.Window, window),
        (QPalette.ColorRole.WindowText, foreground),
        (QPalette.ColorRole.Base, background),
        (QPalette.ColorRole.AlternateBase, alternate),
        (QPalette.ColorRole.Text, foreground),
        (QPalette.ColorRole.Button, window),
        (QPalette.ColorRole.ButtonText, foreground),
        (QPalette.ColorRole.ToolTipBase, background),
        (QPalette.ColorRole.ToolTipText, foreground),
        (QPalette.ColorRole.Highlight, highlight),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.PlaceholderText, disabled),
    ):
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(disabled))
    return palette


def apply_theme(application, theme: str, system_palette: QPalette):
    """Restoring the captured native palette avoids leaking overrides into system mode."""
    application.setPalette(palette_for_theme(theme, system_palette))
