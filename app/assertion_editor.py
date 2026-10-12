"""Dialog to configure assertion rules without manually editing JSON."""
import json

from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)
from .assertions import validate_rules
from .assertion_editor_model import KINDS, describe_rule, parse_rule_fields


class AssertionRuleEditor(QDialog):
    def __init__(self, rules, parent=None):
        super().__init__(parent)
        self.rules = validate_rules(rules)
        self.setWindowTitle("API 응답 검증 규칙 편집")
        self.resize(810, 580)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("검증 규칙을 추가하거나 선택한 규칙을 수정하세요. 저장 전 형식을 검사합니다."))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["검증 유형", "조건"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.select_rule)
        layout.addWidget(self.table)
        panel = QWidget()
        form = QFormLayout(panel)
        self.kind = QComboBox()
        for kind in KINDS:
            self.kind.addItem(kind, kind)
        self.kind.currentIndexChanged.connect(self.update_fields)
        form.addRow("검증 유형", self.kind)
        self.path = QLineEdit()
        self.path.setPlaceholderText("예: data.users[0].id")
        form.addRow("JSON 경로", self.path)
        self.expected = QLineEdit()
        self.expected.setPlaceholderText('상태 코드: 200 / equals 문자열: "hello" / 타입: number')
        form.addRow("예상값", self.expected)
        self.minimum = QLineEdit()
        self.minimum.setPlaceholderText("최솟값 (선택)")
        form.addRow("min", self.minimum)
        self.maximum = QLineEdit()
        self.maximum.setPlaceholderText("최댓값 (선택)")
        form.addRow("max", self.maximum)
        layout.addWidget(panel)
        actions = QHBoxLayout()
        self.add_button = QPushButton("새 규칙 추가")
        self.replace_button = QPushButton("선택 규칙 수정")
        self.remove_button = QPushButton("선택 규칙 삭제")
        self.add_button.clicked.connect(self.add_rule)
        self.replace_button.clicked.connect(self.replace_rule)
        self.remove_button.clicked.connect(self.remove_rule)
        for button in (self.add_button, self.replace_button, self.remove_button):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.count_label = QLabel()
        layout.addWidget(self.count_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()
        self.update_fields()

    def update_fields(self, *_):
        kind = self.kind.currentData()
        self.path.setEnabled(kind != "status")
        self.expected.setEnabled(kind in ("status", "equals", "value_type"))
        self.minimum.setEnabled(kind in ("range", "length"))
        self.maximum.setEnabled(kind in ("range", "length"))

    def refresh(self):
        self.table.setRowCount(len(self.rules))
        for index, rule in enumerate(self.rules):
            self.table.setItem(index, 0, QTableWidgetItem(rule["type"]))
            self.table.setItem(index, 1, QTableWidgetItem(describe_rule(rule)))
        self.table.resizeColumnsToContents()
        self.count_label.setText(f"규칙 {len(self.rules)} / 20개")

    def selected_index(self):
        index = self.table.currentRow()
        return index if 0 <= index < len(self.rules) else None

    def select_rule(self):
        index = self.selected_index()
        if index is None:
            return
        rule = self.rules[index]
        self.kind.setCurrentIndex(self.kind.findData(rule["type"]))
        self.path.setText(rule.get("path", ""))
        expected = rule.get("expected", "")
        self.expected.setText(
            json.dumps(expected, ensure_ascii=False) if rule["type"] == "equals"
            else str(expected))
        self.minimum.setText(str(rule["min"]) if "min" in rule else "")
        self.maximum.setText(str(rule["max"]) if "max" in rule else "")

    def new_rule(self):
        return parse_rule_fields(self.kind.currentData(), self.path.text(),
                                 self.expected.text(), self.minimum.text(),
                                 self.maximum.text())

    def add_rule(self):
        try:
            self.rules = validate_rules([*self.rules, self.new_rule()])
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "규칙 오류", str(exc))
            return
        self.refresh()

    def replace_rule(self):
        index = self.selected_index()
        if index is None:
            QMessageBox.warning(self, "규칙 선택", "수정할 규칙을 먼저 선택하세요.")
            return
        try:
            updated = list(self.rules)
            updated[index] = self.new_rule()
            self.rules = validate_rules(updated)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "규칙 오류", str(exc))
            return
        self.refresh()
        self.table.selectRow(index)

    def remove_rule(self):
        index = self.selected_index()
        if index is None:
            return
        self.rules.pop(index)
        self.refresh()

    def accept(self):
        try:
            self.rules = validate_rules(self.rules)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "규칙 오류", str(exc))
            return
        super().accept()
