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


class RunWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_run = pyqtSignal(str)

    def __init__(self, storage, run_id, endpoints, variables, settings):
        super().__init__()
        self.storage = storage
        self.run_id = run_id
        self.endpoints = endpoints
        self.variables = variables
        self.settings = settings

    def run(self):
        status = "COMPLETED"
        try:
            for endpoint in self.endpoints:
                result = execute(
                    endpoint, self.variables,
                    timeout=self.settings.values["default_timeout_seconds"],
                    verify_ssl=self.settings.values["verify_ssl"],
                    allow_writes=self.settings.values["dangerous_methods_enabled"])
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
        self.setWindowTitle("Postman Tester")
        self.resize(1150, 760)
        self.build_ui()
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
        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.history = QListWidget()
        self.history.currentItemChanged.connect(self.show_history)
        self.report_list = QListWidget()
        for name, widget in [("Request 미리보기", self.request_text),
                             ("Response 예시", self.response_text),
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
        self.environment = {}
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
            return
        index = current.data(0, Qt.ItemDataRole.UserRole)
        if index is None:
            return
        endpoint = self.endpoints[index]
        self.request_text.setPlainText(
            f"{endpoint.method} {endpoint.url}\n\n"
            + json.dumps(endpoint.request, ensure_ascii=False, indent=2)
            + "\n\n--- BODY ---\n" + preview_body(endpoint))
        self.response_text.setPlainText(preview_response(endpoint))

    def start_run(self):
        if not self.current_project() or not self.endpoints:
            QMessageBox.warning(self, "실행 불가", "프로젝트와 Collection을 선택하세요.")
            return
        chosen = self.tree.selectedItems()
        index = chosen[0].data(0, Qt.ItemDataRole.UserRole) if chosen else None
        endpoints = [self.endpoints[index]] if index is not None else list(self.endpoints)
        message = f"API {len(endpoints)}개를 실행합니다.\n쓰기 API는 기본적으로 SKIPPED 처리됩니다.\n계속하시겠습니까?"
        if QMessageBox.question(self, "테스트 시작", message) != QMessageBox.StandardButton.Yes:
            return
        run_id = self.storage.create_run(self.current_project(), "기본 실행")
        self.log_text.append(f"Run ID: {run_id}")
        self.worker = RunWorker(self.storage, run_id, endpoints, self.environment.copy(), self.settings)
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
