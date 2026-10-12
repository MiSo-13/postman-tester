"""Editable, per-project non-secret Environment variables."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget,
                             QTableWidgetItem, QDialogButtonBox, QHBoxLayout, QPushButton,
                             QMessageBox, QAbstractItemView)

from .postman_auth_config import SECRETS


class EnvironmentEditor(QDialog):
    def __init__(self, variables, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Environment 변수 편집")
        self.resize(660, 470)
        self.variables = None
        layout = QVBoxLayout(self)
        note = QLabel("현재 프로젝트의 변수입니다. 변경 내용은 이 프로젝트에 저장됩니다. "
                      "인증 토큰 및 비밀번호는 여기에 입력하지 마세요.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["변수 이름", "값"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for key, value in sorted(variables.items()):
            self.add_row(key, value)
        layout.addWidget(self.table)
        controls = QHBoxLayout()
        add = QPushButton("변수 추가")
        add.clicked.connect(lambda: self.add_row())
        remove = QPushButton("선택 변수 삭제")
        remove.clicked.connect(self.remove_rows)
        controls.addWidget(add)
        controls.addWidget(remove)
        layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def add_row(self, key="", value=""):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(key)))
        self.table.setItem(row, 1, QTableWidgetItem(str(value)))

    def remove_rows(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def accept(self):
        values = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            value_item = self.table.item(row, 1)
            name = (name_item.text() if name_item else "").strip()
            value = value_item.text() if value_item else ""
            if not name or name in values or name in SECRETS:
                QMessageBox.warning(self, "변수 오류", "빈 이름, 중복 이름, 인증 토큰 변수는 사용할 수 없습니다.")
                return
            if not name.replace("_", "").replace("-", "").replace(".", "").isalnum():
                QMessageBox.warning(self, "변수 오류", "변수 이름에 허용되지 않은 문자가 있습니다.")
                return
            values[name] = value
        self.variables = values
        super().accept()
