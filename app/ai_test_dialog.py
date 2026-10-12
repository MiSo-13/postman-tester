"""Non-blocking optional AI planner dialog with human plan review."""
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QCheckBox, QPushButton, QListWidget, QMessageBox,
    QDialogButtonBox)

from .ai_planner_client import generate_plan


class PlanningThread(QThread):
    planned = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, key, model, keys, endpoints, limit, allow_writes):
        super().__init__()
        self.api_key, self.model = key, model
        self.keys, self.endpoints = keys, endpoints
        self.limit, self.allow_writes = limit, allow_writes

    def run(self):
        try:
            self.planned.emit(generate_plan(
                self.api_key, self.model, self.keys, self.endpoints,
                max_steps=self.limit, allow_writes=self.allow_writes))
        except Exception as exc:
            self.failed.emit(str(exc))


class AITestDialog(QDialog):
    def __init__(self, keys, endpoints, parent=None):
        super().__init__(parent)
        self.keys = list(keys)
        self.endpoints = list(endpoints)
        self.plan = None
        self.setWindowTitle("AI 테스트 계획 · 검토")
        self.resize(850, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("AI가 Collection의 API 순서를 제안합니다. 요청 전 계획을 직접 확인하세요."))
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("OpenAI API Key (저장하지 않음)")
        layout.addWidget(self.key)
        self.model = QLineEdit("gpt-5-mini")
        layout.addWidget(QLabel("OpenAI 모델"))
        layout.addWidget(self.model)
        self.limit = QSpinBox()
        self.limit.setRange(1, 30)
        self.limit.setValue(15)
        layout.addWidget(QLabel("최대 테스트 단계"))
        layout.addWidget(self.limit)
        self.writes = QCheckBox("POST/PATCH/PUT/DELETE도 계획에 포함 (실제 실행 허용 설정 별도 적용)")
        layout.addWidget(self.writes)
        self.generate = QPushButton("AI 계획 생성")
        self.generate.clicked.connect(self.request_plan)
        layout.addWidget(self.generate)
        layout.addWidget(QLabel("AI가 제안한 실행 순서 (드래그하여 수정 가능)"))
        self.steps = QListWidget()
        self.steps.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        layout.addWidget(self.steps)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Ok).setText("이 계획으로 실행")
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        layout.addWidget(actions)
        self.worker = None

    def request_plan(self):
        self.generate.setEnabled(False)
        self.plan = None
        self.steps.clear()
        self.worker = PlanningThread(self.key.text(), self.model.text(),
                                     self.keys, self.endpoints,
                                     self.limit.value(), self.writes.isChecked())
        self.worker.planned.connect(self.show_plan)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.generate.setEnabled(True))
        self.worker.start()

    def show_plan(self, plan):
        self.plan = plan
        from PyQt6.QtCore import Qt
        lookup = dict(zip(self.keys, self.endpoints))
        for item in plan["steps"]:
            ep = lookup[item["key"]]
            from PyQt6.QtWidgets import QListWidgetItem
            row = QListWidgetItem(f"{ep.method} {ep.name} — {item['reason']}")
            row.setData(Qt.ItemDataRole.UserRole, item["key"])
            self.steps.addItem(row)

    def show_error(self, message):
        QMessageBox.warning(self, "AI 계획 생성 실패", message)

    def reject(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "계획 생성 중", "AI 응답 처리가 완료된 후 창을 닫을 수 있습니다.")
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)

    def accept(self):
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "생성 중", "계획 생성이 끝나야 실행할 수 있습니다.")
            return
        if not self.plan or not self.steps.count():
            QMessageBox.warning(self, "계획 필요", "먼저 AI 계획을 생성하세요.")
            return
        from PyQt6.QtCore import Qt
        self.selected_keys = [
            self.steps.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.steps.count())]
        super().accept()
