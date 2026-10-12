"""Lightweight Qt trend chart; no network, charts dependency or persisted secrets."""
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget


class TrendChart(QWidget):
    """Draw up to 30 sequential data points, with gaps for missing measurements."""

    def __init__(self, values, title, unit="", parent=None):
        super().__init__(parent)
        self.values = list(values)
        self.title = title
        self.unit = unit
        self.setMinimumHeight(190)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fg = self.palette().color(self.foregroundRole())
        painter.setPen(fg)
        painter.drawText(14, 24, self.title)
        bounds = QRectF(54, 42, max(10, self.width() - 72), max(20, self.height() - 78))
        painter.setPen(QPen(fg, 1))
        painter.drawLine(bounds.bottomLeft(), bounds.topLeft())
        painter.drawLine(bounds.bottomLeft(), bounds.bottomRight())
        numeric = [float(v) for v in self.values if isinstance(v, (int, float))
                   and not isinstance(v, bool) and 0 <= v < float("inf")]
        if not numeric:
            painter.drawText(bounds.toRect(), Qt.AlignmentFlag.AlignCenter, "측정 데이터 없음")
            return
        ceiling = max(numeric)
        floor = min(0.0, min(numeric))
        if ceiling <= floor:
            ceiling = floor + 1.0
        painter.drawText(3, int(bounds.top()) + 5, f"{ceiling:.1f}")
        painter.drawText(3, int(bounds.bottom()), f"{floor:.1f}")
        last = None
        for i, value in enumerate(self.values):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value < float("inf"):
                last = None
                continue
            x = bounds.left() + bounds.width() * i / max(1, len(self.values) - 1)
            y = bounds.bottom() - bounds.height() * (value - floor) / (ceiling - floor)
            if last is not None:
                painter.setPen(QPen(QColor("#2770a8"), 2))
                painter.drawLine(last[0], last[1], int(x), int(y))
            painter.setPen(QPen(QColor("#2770a8"), 2))
            painter.setBrush(QColor("#2770a8"))
            painter.drawEllipse(QRectF(x - 3, y - 3, 6, 6))
            last = (int(x), int(y))
        painter.setPen(fg)
        painter.drawText(int(bounds.left()), self.height() - 9, "과거")
        painter.drawText(int(bounds.right()) - 24, self.height() - 9, "최근")
