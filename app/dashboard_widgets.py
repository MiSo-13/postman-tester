"""Operational dashboard KPI cards, separate from analytics aggregation."""
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame


class MetricCard(QFrame):
    def __init__(self, label, value, hint="", tone="neutral", parent=None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setProperty("tone", tone)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 12, 15, 12)
        title = QLabel(label)
        title.setObjectName("MetricLabel")
        self.value = QLabel(str(value))
        self.value.setObjectName("MetricValue")
        note = QLabel(hint)
        note.setObjectName("MetricHint")
        layout.addWidget(title)
        layout.addWidget(self.value)
        layout.addWidget(note)


class DashboardMetrics(QWidget):
    """Visible, compact operations scorecard; inputs come from build_dashboard."""
    def __init__(self, data, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        total = data["executed"]
        failures = data["failures"]
        passed = total - failures
        rate = data["failure_rate"]
        latency = data["avg_ms"]
        cards = [
            ("PASS", f"{passed:,}", "성공 요청", "success"),
            ("FAIL / ERROR", f"{failures:,}", "실패 및 차단", "error"),
            ("실패율", f"{rate:.1f}%" if rate is not None else "—", "SKIPPED 제외", "warning"),
            ("평균 응답", f"{latency:.0f} ms" if latency is not None else "—", "측정된 요청", "neutral"),
            ("실행 회차", f"{data['runs']:,}", f"SKIPPED {data['skipped']:,}", "neutral"),
        ]
        self.cards = []
        for label, value, hint, tone in cards:
            card = MetricCard(label, value, hint, tone)
            self.cards.append(card)
            layout.addWidget(card, 1)
