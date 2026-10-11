"""Initial functional PyQt6 shell with import, safe test runs and persistent history."""
import json
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel,
    QComboBox, QFileDialog, QMessageBox, QInputDialog, QSplitter,
    QTabWidget, QListWidget, QCheckBox
)

from .settings import Settings
from .storage import Storage
from .postman import parse_collection, parse_environment, preview_body, preview_response, Endpoint
from .templates import save_examples
from .runner import execute
from .reports import export_reports
from .request_overrides import endpoint_key, validate_raw_json


class RunWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_run = pyqtSignal(str)

    def __init__(self, storage, run_id, endpoints, variables, settings, body_overrides):
        super().__init__()
        self.storage = storage
        self.run_id = run_id
        self.endpoints = endpoints
        self.variables = variables
        self.settings = settings
        self.body_overrides = body_overrides

    def run(self):
        status = "COMPLETED"
        try:
            for key, endpoint in self.endpoints:
                result = execute(
                    endpoint, self.variables,
                    timeout=self.settings.values["default_timeout_seconds"],
                    verify_ssl=self.settings.values["verify_ssl"],
                    allow_writes=self.settings.values["dangerous_methods_enabled"],
                    raw_body_override=self.body_overrides.get(key))
                self.storage.add_result(
                    self.run_id, endpoint.name, endpoint.method, endpoint.url, **result)
                self.progress.emit(endpoint.name, result["status"])
        except Exception as exc:
            status = "ERROR"
            self.progress.emit("실행 오류", str(exc))
        finally:
            self.storage.finish_run(self.run_id, status)
            self.finished_run.emit(self.run_id)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = Settings()
        self.storage = Storage(self.settings.data_path())
        self.endpoints = []
        self.environment = {}
        self.endpoint_keys = []
        self.selected_endpoint_index = None
        self.setWindowTitle("Postman Tester")
        self.resize(1150, 760)
        self.build_ui()
        self.body_editor.setEnabled(False)
        self.body_save.setEnabled(False)
        self.body_reset.setEnabled(False)
        self.refresh_projects()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.projects = QComboBox()
        self.projects.currentIndexChanged.connect(self.project_changed)
        top.addWidget(QLabel("프로젝트"))
        top.addWidget(self.projects, 2)
        for label, callback in [
            ("새 프로젝트", self.add_project), ("Collection Import", self.import_collection),
            ("Environment Import", self.import_environment),
            ("예제 JSON 내려받기", self.download_examples),
            ("테스트 실행", self.start_run),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            top.addWidget(button)
        layout.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["API", "Method"])
        self.tree.currentItemChanged.connect(self.show_endpoint)
        splitter.addWidget(self.tree)

        tabs = QTabWidget()
        self.request_text = QTextEdit()
        self.request_text.setReadOnly(True)
        self.body_editor = QTextEdit()
        self.body_editor.setPlaceholderText("Raw JSON Body (주석 지원)")
        self.body_editor.textChanged.connect(self.on_body_changed)
        self.body_save = QPushButton("JSON 수정 저장")
        self.body_save.clicked.connect(self.save_body)
        self.body_reset = QPushButton("원본으로 복원")
        self.body_reset.clicked.connect(self.reset_body)
        self.body_message = QLabel("Raw JSON API를 선택하세요.")
        body_panel = QWidget()
        body_layout = QVBoxLayout(body_panel)
        body_layout.addWidget(self.body_editor)
        actions = QHBoxLayout()
        actions.addWidget(self.body_save)
        actions.addWidget(self.body_reset)
        body_layout.addLayout(actions)
        body_layout.addWidget(self.body_message)
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.history = QListWidget()
        self.history.currentItemChanged.connect(self.show_history)
        self.report_list = QListWidget()
        for name, widget in [("Request 미리보기", self.request_text),
                             ("Response 예시", self.response_text),
                             ("JSON Body 편집", body_panel),
                             ("실행 로그", self.log_text),
                             ("이전 실행", self.history),
                             ("보관된 보고서", self.report_list)]:
            tabs.addTab(widget, name)
        splitter.addWidget(tabs)
        splitter.setSizes([420, 720])
        layout.addWidget(splitter)
        self.statusBar().showMessage("Collection을 가져와 시작하세요.")

    def current_project(self):
        return self.projects.currentData()

    def refresh_projects(self):
        self.projects.blockSignals(True)
        self.projects.clear()
        for item in self.storage.projects():
            self.projects.addItem(item["name"], item["id"])
        last = self.settings.values["last_project_id"]
        idx = self.projects.findData(last)
        self.projects.setCurrentIndex(idx if idx >= 0 else (0 if self.projects.count() else -1))
        self.projects.blockSignals(False)
        self.project_changed()

    def add_project(self):
        name, ok = QInputDialog.getText(self, "프로젝트 추가", "프로젝트 이름")
        if ok and name.strip():
            identifier = self.storage.create_project(name)
            self.settings.set("last_project_id", identifier)
            self.refresh_projects()

    def project_changed(self, *_):
        project = self.current_project()
        self.tree.clear()
        self.endpoints = []
        self.endpoint_keys = []
        self.selected_endpoint_index = None
        self.environment = {}
        self.body_editor.blockSignals(True)
        self.body_editor.clear()
        self.body_editor.blockSignals(False)
        self.history.clear()
        self.report_list.clear()
        if not project:
            return
        self.settings.set("last_project_id", project)
        imported = self.storage.latest_import(project, "collection")
        if imported:
            from tempfile import NamedTemporaryFile
            # Import source is persisted in SQLite, never relies on the original path.
            document = json.loads(imported["content"])
            self.load_collection_document(document)
        environment = self.storage.latest_import(project, "environment")
        if environment:
            doc = json.loads(environment["content"])
            self.environment = {v["key"]: v.get("value", "") for v in doc.get("values", [])
                                if v.get("enabled", True) and "key" in v}
        self.refresh_history()

    def load_collection_document(self, document):
        from .postman import endpoints_from_document
        self.endpoints = endpoints_from_document(document)
        seen = {}
        self.endpoint_keys = []
        for endpoint in self.endpoints:
            signature = (endpoint.folder, endpoint.name, endpoint.method, endpoint.url)
            ordinal = seen.get(signature, 0)
            seen[signature] = ordinal + 1
            self.endpoint_keys.append(endpoint_key(endpoint, ordinal))
        self.tree.clear()
        groups = {}
        for index, endpoint in enumerate(self.endpoints):
            folder = endpoint.folder or "기본"
            parent = groups.get(folder)
            if parent is None:
                parent = QTreeWidgetItem([folder, ""])
                self.tree.addTopLevelItem(parent)
                groups[folder] = parent
            item = QTreeWidgetItem([endpoint.name, endpoint.method])
            item.setData(0, Qt.ItemDataRole.UserRole, index)
            parent.addChild(item)
        self.tree.expandAll()
        self.statusBar().showMessage(f"API {len(self.endpoints)}개 로드 완료")

    def import_collection(self):
        if not self.current_project():
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 먼저 만드세요.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Collection 선택", "", "JSON (*.json)")
        if not filename:
            return
        try:
            document, _ = parse_collection(filename)
            self.storage.save_import(self.current_project(), "collection", Path(filename).name, document)
            self.load_collection_document(document)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import 오류", str(exc))

    def import_environment(self):
        if not self.current_project():
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 먼저 만드세요.")
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Environment 선택", "", "JSON (*.json)")
        if not filename:
            return
        try:
            self.environment = parse_environment(filename)
            document = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            self.storage.save_import(self.current_project(), "environment", Path(filename).name, document)
            self.statusBar().showMessage(f"변수 {len(self.environment)}개 로드 완료")
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import 오류", str(exc))

    def download_examples(self):
        folder = QFileDialog.getExistingDirectory(self, "예제 JSON 저장 폴더")
        if folder:
            paths = save_examples(Path(folder))
            QMessageBox.information(self, "완료", "생성된 파일:\n" + "\n".join(map(str, paths)))

    def show_endpoint(self, current, previous):
        if current is None:
            self.selected_endpoint_index = None
            self.body_editor.setEnabled(False)
            return
        index = current.data(0, Qt.ItemDataRole.UserRole)
        if index is None:
            self.selected_endpoint_index = None
            self.body_editor.setEnabled(False)
            return
        self.selected_endpoint_index = index
        endpoint = self.endpoints[index]
        self.request_text.setPlainText(
            f"{endpoint.method} {endpoint.url}\n\n"
            + json.dumps(endpoint.request, ensure_ascii=False, indent=2)
            + "\n\n--- BODY ---\n" + preview_body(endpoint))
        self.response_text.setPlainText(preview_response(endpoint))
        body = endpoint.request.get("body", {})
        editable = body.get("mode") == "raw" and body.get("options", {}).get("raw", {}).get("language", "json") == "json"
        self.body_editor.setEnabled(editable)
        self.body_save.setEnabled(editable)
        self.body_reset.setEnabled(editable)
        self.body_editor.blockSignals(True)
        original = body.get("raw", "") if editable else ""
        saved = self.storage.get_request_override(self.current_project(), self.endpoint_keys[index]) if editable else None
        self.body_editor.setPlainText(saved if saved is not None else original)
        self.body_editor.blockSignals(False)
        self.body_message.setText("저장된 수정값" if saved is not None else
                                  "원본 JSON (저장하면 프로젝트별로 보존)" if editable else
                                  "이 API에는 편집 가능한 Raw JSON Body가 없습니다.")

    def on_body_changed(self):
        if self.selected_endpoint_index is not None:
            self.body_message.setText("저장되지 않은 수정사항")

    def save_body(self):
        index = self.selected_endpoint_index
        if index is None or not self.body_editor.isEnabled():
            return
        raw = self.body_editor.toPlainText()
        try:
            validate_raw_json(raw)
        except ValueError as exc:
            QMessageBox.warning(self, "JSON 검증 실패", str(exc))
            return
        self.storage.save_request_override(self.current_project(), self.endpoint_keys[index], raw)
        self.body_message.setText("저장 완료 — 앱을 재시작해도 유지됩니다.")
        self.statusBar().showMessage("Request JSON 수정값을 저장했습니다.")

    def reset_body(self):
        index = self.selected_endpoint_index
        if index is None or not self.body_editor.isEnabled():
            return
        if QMessageBox.question(self, "원본 복원", "저장된 수정값을 삭제하고 Collection 원본으로 복원합니까?") != QMessageBox.StandardButton.Yes:
            return
        self.storage.remove_request_override(self.current_project(), self.endpoint_keys[index])
        original = self.endpoints[index].request.get("body", {}).get("raw", "")
        self.body_editor.blockSignals(True)
        self.body_editor.setPlainText(original)
        self.body_editor.blockSignals(False)
        self.body_message.setText("원본으로 복원되었습니다.")

    def start_run(self):
        if self.body_message.text() == "저장되지 않은 수정사항":
            QMessageBox.warning(
                self, "저장되지 않은 JSON",
                "JSON Body 편집 내용이 저장되지 않았습니다. 먼저 'JSON 수정 저장'을 눌러주세요.")
            return
        if not self.current_project() or not self.endpoints:
            QMessageBox.warning(self, "실행 불가", "프로젝트와 Collection을 선택하세요.")
            return
        chosen = self.tree.selectedItems()
        index = chosen[0].data(0, Qt.ItemDataRole.UserRole) if chosen else None
        indices = [index] if index is not None else list(range(len(self.endpoints)))
        endpoints = [(self.endpoint_keys[i], self.endpoints[i]) for i in indices]
        message = f"API {len(endpoints)}개를 실행합니다.\n쓰기 API는 기본적으로 SKIPPED 처리됩니다.\n계속하시겠습니까?"
        if QMessageBox.question(self, "테스트 시작", message) != QMessageBox.StandardButton.Yes:
            return
        run_id = self.storage.create_run(self.current_project(), "기본 실행")
        self.log_text.append(f"Run ID: {run_id}")
        body_overrides = {
            key: stored for key, _ in endpoints
            if (stored := self.storage.get_request_override(self.current_project(), key)) is not None
        }
        self.worker = RunWorker(
            self.storage, run_id, endpoints, self.environment.copy(), self.settings,
            body_overrides)
        self.worker.progress.connect(lambda name, state: self.log_text.append(f"[{state}] {name}"))
        self.worker.finished_run.connect(self.run_finished)
        self.worker.start()
        self.statusBar().showMessage("테스트 실행 중")

    def run_finished(self, run_id):
        try:
            paths = export_reports(self.storage, run_id, self.settings.data_path() / "reports" / run_id)
            self.log_text.append("보고서 보존: " + ", ".join(map(str, paths)))
        except Exception as exc:
            self.log_text.append(f"보고서 오류: {exc}")
        self.refresh_history()
        self.statusBar().showMessage("테스트 종료 및 이력 저장 완료")

    def refresh_history(self):
        self.history.clear()
        if self.current_project():
            for run in self.storage.runs(self.current_project()):
                self.history.addItem(f"{run['started_at']}  [{run['status']}]  {run['id']}")

    def show_history(self, current, previous):
        self.report_list.clear()
        if not current:
            return
        run_id = current.text().split()[-1]
        results = self.storage.results(run_id)
        self.log_text.setPlainText("\n".join(
            f"[{r['status']}] {r['method']} {r['url']} ({r['http_status']}) {r['detail']}"
            for r in results))
        for report in self.storage.reports(run_id):
            self.report_list.addItem(f"{report['format'].upper()}  {report['file_path']}")


def launch():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
