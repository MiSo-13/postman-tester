"""Select redacted JSON response fields and propose assertion rules."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTreeWidget,
                             QTreeWidgetItem, QComboBox, QDialogButtonBox, QMessageBox)
from .response_assertion_candidates import candidates_from_preview, rule_from_candidate


class ResponseFieldRuleDialog(QDialog):
    def __init__(self, preview, parent=None):
        super().__init__(parent)
        self.setWindowTitle("응답 필드로 검증 규칙 만들기")
        self.resize(690, 510)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("필드를 선택한 뒤 검증 종류를 지정하세요. 마스킹된 값은 존재 확인만 지원합니다."))
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["JSON 경로", "값 유형"])
        for path, value in candidates_from_preview(preview):
            kind = type(value).__name__
            if isinstance(value, str) and value.startswith("[") and value.endswith("]"):
                kind = "마스킹된 값"
            item = QTreeWidgetItem([path, kind])
            item.setData(0, Qt.ItemDataRole.UserRole, (path, value))
            self.tree.addTopLevelItem(item)
        layout.addWidget(self.tree)
        self.kind = QComboBox()
        for label, key in (("필드 존재", "exists"), ("데이터 타입", "value_type"),
                           ("값 일치 (숫자·불리언·null)", "equals")):
            self.kind.addItem(label, key)
        layout.addWidget(self.kind)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.rule = None

    def accept(self):
        selected = self.tree.currentItem()
        if not selected:
            QMessageBox.warning(self, "필드 선택", "검증할 필드를 선택하세요.")
            return
        path, value = selected.data(0, Qt.ItemDataRole.UserRole)
        try:
            self.rule = rule_from_candidate(path, value, self.kind.currentData())
        except ValueError as exc:
            QMessageBox.warning(self, "규칙 생성 불가", str(exc))
            return
        super().accept()
