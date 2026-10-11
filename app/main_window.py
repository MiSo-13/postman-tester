"""Initial functional PyQt6 shell with import, safe test runs and persistent history."""
import json
import sys
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel,
    QComboBox, QFileDialog, QMessageBox, QInputDialog, QSplitter,
    QTabWidget, QListWidget, QListWidgetItem, QCheckBox, QLineEdit, QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QAbstractItemView
)

from .settings import Settings
from .storage import Storage
from .postman import parse_collection, parse_environment, preview_body, preview_response, Endpoint
from .templates import save_examples
from .runner import execute
from .reports import export_reports
from .user_auth import login_tokens, refresh_tokens, needs_user_token, needs_admin_token, LoginError, DEFAULT_LOGIN_CONFIGS
from .request_overrides import endpoint_key, validate_raw_json
from .scenarios import resolve_steps, validate_steps, should_stop
from .retry import retry_candidates
from .run_comparison import compare_runs


class RunWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_run = pyqtSignal(str)
    step_result = pyqtSignal(int, int, str, str)

    def __init__(self, storage, run_id, endpoints, variables, settings, body_overrides, user_credentials=None, admin_credentials=None, auth_configs=None, response_rules=None, extraction_rules=None, stop_on_failure=False):
        super().__init__()
        self.storage = storage
        self.run_id = run_id
        self.endpoints = endpoints
        self.variables = variables
        self.settings = settings
        self.body_overrides = body_overrides
        self.user_credentials = user_credentials
        self.admin_credentials = admin_credentials
        self.auth_configs = auth_configs or {}
        self.response_rules = response_rules or {}
        self.extraction_rules = extraction_rules or {}
        self.stop_on_failure = stop_on_failure

    def run(self):
        status = "COMPLETED"
        try:
            sessions = {"USER": None, "ADMIN": None}
            profiles = (
                ("USER", self.user_credentials, needs_user_token),
                ("ADMIN", self.admin_credentials, needs_admin_token),
            )
            for profile, credentials, checker in profiles:
                if credentials and any(checker(e) for _, e in self.endpoints):
                    try:
                        sessions[profile] = login_tokens(
                            profile, self.variables.get("baseUrl", ""), *credentials,
                            timeout=self.settings.values["default_timeout_seconds"],
                            verify_ssl=self.settings.values["verify_ssl"],
                            config=self.auth_configs.get(profile))
                        self.progress.emit(f"{profile} 로그인", "PASS")
                    except LoginError as exc:
                        self.progress.emit(f"{profile} 로그인", f"ERROR: {exc}")
                        status = "ERROR"
                        return
            for step_index, (key, endpoint) in enumerate(self.endpoints, start=1):
                selected_profile = ("USER" if needs_user_token(endpoint) else
                                    "ADMIN" if needs_admin_token(endpoint) else None)
                user_token = sessions["USER"][0] if sessions["USER"] else None
                admin_token = sessions["ADMIN"][0] if sessions["ADMIN"] else None
                result = execute(
                    endpoint, self.variables,
                    timeout=self.settings.values["default_timeout_seconds"],
                    verify_ssl=self.settings.values["verify_ssl"],
                    allow_writes=self.settings.values["dangerous_methods_enabled"],
                    raw_body_override=self.body_overrides.get(key),
                    user_access_token=user_token,
                    admin_access_token=admin_token,
                    file_root=self.settings.root / self.settings.values["file_root"],
                    assertions=self.response_rules.get(key, []),
                    extraction_rules=self.extraction_rules.get(key, []),
                    captured_variables=self.variables)
                # Only read-only requests may be automatically replayed after 401.
                if (selected_profile and result.get("http_status") == 401
                        and endpoint.method.upper() in ("GET", "HEAD", "OPTIONS")
                        and sessions[selected_profile] and sessions[selected_profile][1]):
                    try:
                        sessions[selected_profile] = refresh_tokens(
                            selected_profile, self.variables.get("baseUrl", ""),
                            sessions[selected_profile][1],
                            timeout=self.settings.values["default_timeout_seconds"],
                            verify_ssl=self.settings.values["verify_ssl"])
                        self.progress.emit(f"{selected_profile} 토큰 갱신", "PASS")
                        user_token = sessions["USER"][0] if sessions["USER"] else None
                        admin_token = sessions["ADMIN"][0] if sessions["ADMIN"] else None
                        result = execute(
                            endpoint, self.variables,
                            timeout=self.settings.values["default_timeout_seconds"],
                            verify_ssl=self.settings.values["verify_ssl"],
                            allow_writes=self.settings.values["dangerous_methods_enabled"],
                            raw_body_override=self.body_overrides.get(key),
                            user_access_token=user_token,
                            admin_access_token=admin_token,
                            assertions=self.response_rules.get(key, []),
                            extraction_rules=self.extraction_rules.get(key, []),
                            captured_variables=self.variables)
                    except LoginError as exc:
                        self.progress.emit(f"{selected_profile} 토큰 갱신", f"ERROR: {exc}")
                        result["status"] = "ERROR"
                        result["detail"] = f"{selected_profile} 토큰 갱신 실패"
                self.storage.add_result(
                    self.run_id, endpoint.name, endpoint.method, endpoint.url, **result)
                self.progress.emit(endpoint.name, result["status"])
                self.step_result.emit(step_index, len(self.endpoints), endpoint.name, result["status"])
                if should_stop(result["status"], self.stop_on_failure):
                    status = "STOPPED"
                    break
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
            ("로그인 설정", self.configure_logins),
            ("응답 검증 규칙", self.configure_assertions),
            ("응답 변수 추출", self.configure_extractions),
            ("시나리오 관리", self.manage_scenarios),
            ("실행 회차 비교", self.compare_run_history),
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
        self.result_table = QTableWidget(0, 6)
        self.result_table.setHorizontalHeaderLabels(
            ["API", "Method", "상태", "HTTP", "시간(ms)", "상세"])
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.retry_button = QPushButton("선택한 실패 읽기 API 재실행")
        self.retry_button.clicked.connect(self.retry_failed)
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        results_layout.addWidget(self.result_table)
        results_layout.addWidget(self.retry_button)
        self.report_list = QListWidget()
        for name, widget in [("Request 미리보기", self.request_text),
                             ("Response 예시", self.response_text),
                             ("JSON Body 편집", body_panel),
                             ("실행 로그", self.log_text),
                             ("이전 실행", self.history),
                             ("실행 결과 상세", results_panel),
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

    def configure_logins(self):
        project = self.current_project()
        if not project:
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 먼저 만드세요.")
            return
        for profile in ("USER", "ADMIN"):
            original = self.storage.get_auth_config(project, profile) or DEFAULT_LOGIN_CONFIGS[profile]
            updated = {}
            for field, label in (
                ("endpoint", "로그인 Endpoint (상대 경로)"),
                ("identifier_key", "계정 ID 요청 필드명"),
                ("password_key", "비밀번호 요청 필드명"),
            ):
                value, ok = QInputDialog.getText(
                    self, f"{profile} 로그인 설정", label, text=original[field])
                if not ok:
                    return
                updated[field] = value.strip()
            try:
                self.storage.save_auth_config(project, profile, updated)
            except ValueError as exc:
                QMessageBox.warning(self, "인증 설정 오류", str(exc))
                return
        QMessageBox.information(self, "저장 완료", "USER/ADMIN 로그인 설정을 저장했습니다.\\n계정과 비밀번호는 저장하지 않습니다.")

    def configure_assertions(self):
        index = self.selected_endpoint_index
        if index is None or not self.current_project():
            QMessageBox.warning(self, "API 선택 필요", "검증할 API를 먼저 선택하세요.")
            return
        key = self.endpoint_keys[index]
        existing = self.storage.get_response_assertions(self.current_project(), key)
        raw, ok = QInputDialog.getMultiLineText(
            self, "응답 검증 규칙", "JSON 규칙 배열 (status / exists / equals)",
            json.dumps(existing, ensure_ascii=False, indent=2))
        if not ok:
            return
        try:
            rules = json.loads(raw)
            self.storage.save_response_assertions(self.current_project(), key, rules)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "규칙 오류", str(exc))
            return
        self.statusBar().showMessage("선택 API의 응답 검증 규칙을 저장했습니다.")

    def configure_extractions(self):
        index = self.selected_endpoint_index
        if index is None or not self.current_project():
            QMessageBox.warning(self, "API 선택 필요", "변수를 추출할 API를 먼저 선택하세요.")
            return
        key = self.endpoint_keys[index]
        existing = self.storage.get_response_extractions(self.current_project(), key)
        raw, ok = QInputDialog.getMultiLineText(
            self, "응답 변수 추출", "JSON 배열: [{\"name\":\"userId\",\"path\":\"data.userId\"}]",
            json.dumps(existing, ensure_ascii=False, indent=2))
        if not ok:
            return
        try:
            rules = json.loads(raw)
            self.storage.save_response_extractions(self.current_project(), key, rules)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "추출 규칙 오류", str(exc))
            return
        self.statusBar().showMessage("추출 규칙을 저장했습니다. 변수 값은 실행 중에만 유지됩니다.")

    def manage_scenarios(self):
        project = self.current_project()
        if not project or not self.endpoints:
            QMessageBox.warning(self, "준비 필요", "프로젝트와 Collection을 선택하세요.")
            return
        saved = self.storage.scenarios(project)
        labels = ["새 시나리오"] + [f"{x['name']} ({x['id'][:8]})" for x in saved]
        choice, ok = QInputDialog.getItem(self, "시나리오 관리", "관리할 시나리오", labels, 0, False)
        if not ok:
            return
        selection = labels.index(choice)
        item = saved[selection - 1] if selection else None
        if item:
            decision = QMessageBox.question(
                self, "시나리오 관리", "삭제하시겠습니까? 아니오를 누르면 편집합니다.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Cancel)
            if decision == QMessageBox.StandardButton.Cancel:
                return
            if decision == QMessageBox.StandardButton.Yes:
                self.storage.delete_scenario(project, item["id"])
                return
        name, ok = QInputDialog.getText(
            self, "시나리오 이름", "이름", text=item["name"] if item else "")
        if not ok:
            return
        steps = json.loads(item["steps_json"]) if item else list(self.endpoint_keys)
        try:
            validate_steps(steps, self.endpoint_keys)
        except ValueError as exc:
            QMessageBox.warning(self, "시나리오 오류", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("시나리오 편집 (드래그로 순서 변경)")
        dialog.resize(550, 520)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("아래 목록에서 행을 드래그해 실행 순서를 변경하세요."))
        available = QComboBox()
        for i, endpoint in enumerate(self.endpoints):
            available.addItem(f"{i+1}. {endpoint.method} {endpoint.name}", self.endpoint_keys[i])
        layout.addWidget(available)
        ordered = QListWidget()
        ordered.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        for key in steps:
            ep = self.endpoints[self.endpoint_keys.index(key)]
            row = QListWidgetItem(f"{ep.method} {ep.name}")
            row.setData(Qt.ItemDataRole.UserRole, key)
            ordered.addItem(row)
        layout.addWidget(ordered)
        actions = QHBoxLayout()
        add = QPushButton("API 추가")
        remove = QPushButton("선택 단계 삭제")
        def add_step():
            item = QListWidgetItem(available.currentText())
            item.setData(Qt.ItemDataRole.UserRole, available.currentData())
            ordered.addItem(item)
        add.clicked.connect(add_step)
        remove.clicked.connect(lambda: ordered.takeItem(ordered.currentRow())
                               if ordered.currentRow() >= 0 else None)
        actions.addWidget(add)
        actions.addWidget(remove)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            keys = validate_steps(
                [ordered.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(ordered.count())], self.endpoint_keys)
            self.storage.save_scenario(project, name, keys, item["id"] if item else None)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "시나리오 오류", str(exc))
            return
        self.statusBar().showMessage("시나리오가 저장되었습니다.")

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

    def start_run(self, checked=False, *, retry_endpoints=None):
        if self.body_message.text() == "저장되지 않은 수정사항":
            QMessageBox.warning(
                self, "저장되지 않은 JSON",
                "JSON Body 편집 내용이 저장되지 않았습니다. 먼저 'JSON 수정 저장'을 눌러주세요.")
            return
        if not self.current_project() or not self.endpoints:
            QMessageBox.warning(self, "실행 불가", "프로젝트와 Collection을 선택하세요.")
            return
        if retry_endpoints is not None:
            endpoints = retry_endpoints
            scenario_name = '실패 읽기 API 재실행'
        else:
            chosen = self.tree.selectedItems()
            index = chosen[0].data(0, Qt.ItemDataRole.UserRole) if chosen else None
            scenarios = self.storage.scenarios(self.current_project())
            scenario_name = None
            if scenarios and index is None:
                labels = ["전체 Collection 순서"] + [
                    f"{s['name']} ({s['id'][:8]})" for s in scenarios]
                choice, ok = QInputDialog.getItem(
                    self, "실행 시나리오", "실행할 시나리오 선택", labels, 0, False)
                if not ok:
                    return
                selection = labels.index(choice)
                if selection:
                    entry = scenarios[selection - 1]
                    scenario_name = entry["name"]
                    try:
                        endpoints = resolve_steps(
                            json.loads(entry["steps_json"]), self.endpoint_keys, self.endpoints)
                    except ValueError as exc:
                        QMessageBox.warning(self, "시나리오 오류", str(exc))
                        return
                else:
                    endpoints = list(zip(self.endpoint_keys, self.endpoints))
            else:
                indices = [index] if index is not None else list(range(len(self.endpoints)))
                endpoints = [(self.endpoint_keys[i], self.endpoints[i]) for i in indices]
        message = f"API {len(endpoints)}개를 실행합니다.\n쓰기 API는 기본적으로 SKIPPED 처리됩니다.\n계속하시겠습니까?"
        if QMessageBox.question(self, "테스트 시작", message) != QMessageBox.StandardButton.Yes:
            return
        choice, ok = QInputDialog.getItem(self, "실패 처리 정책",
            "FAIL / ERROR / BLOCKED 발생 시", ["계속 실행", "즉시 중단"], 0, False)
        if not ok:
            return
        stop_on_failure = choice == "즉시 중단"
        user_credentials = None
        if any(needs_user_token(e) for _, e in endpoints):
            answer = QMessageBox.question(
                self, "USER 자동 로그인",
                "선택한 API에 USER Bearer 인증이 필요합니다.\n"
                "계정으로 로그인 후 토큰을 적용하시겠습니까?\n"
                "계정 및 토큰은 앱에 저장되지 않습니다.")
            if answer == QMessageBox.StandardButton.Yes:
                email, ok = QInputDialog.getText(self, "USER 로그인", "userEmail")
                if not ok or not email.strip():
                    return
                password, ok = QInputDialog.getText(
                    self, "USER 로그인", "userPassword", QLineEdit.EchoMode.Password)
                if not ok or not password:
                    return
                user_credentials = (email.strip(), password)
        admin_credentials = None
        if any(needs_admin_token(e) for _, e in endpoints):
            answer = QMessageBox.question(
                self, "ADMIN 자동 로그인",
                "관리자 인증이 필요한 API가 있습니다. 로그인하시겠습니까?\n"
                "계정 및 토큰은 저장되지 않습니다.")
            if answer == QMessageBox.StandardButton.Yes:
                admin_id, ok = QInputDialog.getText(self, "ADMIN 로그인", "adminId")
                if not ok or not admin_id.strip():
                    return
                password, ok = QInputDialog.getText(
                    self, "ADMIN 로그인", "adminPw", QLineEdit.EchoMode.Password)
                if not ok or not password:
                    return
                admin_credentials = (admin_id.strip(), password)
        body_overrides = {
            key: stored for key, _ in endpoints
            if (stored := self.storage.get_request_override(self.current_project(), key)) is not None
        }
        auth_configs = {
            profile: self.storage.get_auth_config(self.current_project(), profile)
                     or DEFAULT_LOGIN_CONFIGS[profile]
            for profile in ("USER", "ADMIN")
        }
        response_rules = {
            key: self.storage.get_response_assertions(self.current_project(), key)
            for key, _ in endpoints
        }
        extraction_rules = {
            key: self.storage.get_response_extractions(self.current_project(), key)
            for key, _ in endpoints
        }
        run_id = self.storage.create_run(self.current_project(), scenario_name or '기본 실행')
        self.log_text.append(f'Run ID: {run_id}')
        self.worker = RunWorker(
            self.storage, run_id, endpoints, self.environment.copy(), self.settings,
            body_overrides, user_credentials, admin_credentials, auth_configs, response_rules, extraction_rules,
            stop_on_failure=stop_on_failure)
        self.worker.progress.connect(lambda name, state: self.log_text.append(f"[{state}] {name}"))
        self.worker.step_result.connect(lambda i, total, name, state: self.log_text.append(f'단계 {i}/{total}: [{state}] {name}'))
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

    def compare_run_history(self):
        if not self.current_project():
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 선택하세요.")
            return
        runs = [r for r in self.storage.runs(self.current_project())
                if r["status"] != "PENDING"]
        if len(runs) < 2:
            QMessageBox.warning(self, "회차 부족", "완료된 실행 회차가 최소 2개 필요합니다.")
            return
        labels = [f"{r['started_at']} [{r['status']}] {r['name']} ({r['id'][:8]})"
                  for r in runs]
        older, ok = QInputDialog.getItem(
            self, "회차 비교", "기준 회차 (이전)", labels, 1, False)
        if not ok:
            return
        newer, ok = QInputDialog.getItem(
            self, "회차 비교", "비교 회차 (이후)", labels, 0, False)
        if not ok:
            return
        i, j = labels.index(older), labels.index(newer)
        if i == j:
            QMessageBox.warning(self, "회차 선택 오류", "서로 다른 회차를 선택하세요.")
            return
        changes = compare_runs(
            self.storage.results(runs[i]["id"]),
            self.storage.results(runs[j]["id"]))
        dialog = QDialog(self)
        dialog.setWindowTitle("실행 회차 비교")
        dialog.resize(900, 550)
        layout = QVBoxLayout(dialog)
        summary = {}
        for item in changes:
            summary[item["change"]] = summary.get(item["change"], 0) + 1
        layout.addWidget(QLabel(" | ".join(
            f"{k}: {v}" for k, v in sorted(summary.items())) or "비교 대상 없음"))
        table = QTableWidget(len(changes), 7)
        table.setHorizontalHeaderLabels(
            ["API", "Method", "순번", "기준", "비교", "변화", "시간차(ms)"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for row, item in enumerate(changes):
            values = [item["name"], item["method"], item["occurrence"],
                      item["before"], item["after"], item["change"], item["delta_ms"]]
            for col, value in enumerate(values):
                table.setItem(row, col, QTableWidgetItem(
                    "—" if value is None else str(value)))
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def retry_failed(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            QMessageBox.warning(self, "실행 중", "현재 실행이 끝난 후 재실행하세요.")
            return
        current = self.history.currentItem()
        if current is None:
            QMessageBox.warning(self, "회차 선택 필요", "이전 실행 회차를 먼저 선택하세요.")
            return
        run_id = current.text().split()[-1]
        rows = self.storage.results(run_id)
        selected_rows = sorted(set(index.row() for index in self.result_table.selectedIndexes()))
        if selected_rows:
            rows = [rows[i] for i in selected_rows]
        candidates = retry_candidates(rows, self.endpoints, self.endpoint_keys)
        if not candidates:
            QMessageBox.warning(self, "재실행 불가",
                "실패한 GET/HEAD/OPTIONS 요청만 재실행할 수 있습니다.")
            return
        self.start_run(retry_endpoints=candidates)

    def show_history(self, current, previous):
        self.report_list.clear()
        self.result_table.setRowCount(0)
        if not current:
            return
        run_id = current.text().split()[-1]
        results = self.storage.results(run_id)
        self.result_table.setRowCount(len(results))
        for i, result in enumerate(results):
            values = [result["endpoint_name"], result["method"], result["status"],
                      result["http_status"], result["elapsed_ms"], result["detail"]]
            for column, value in enumerate(values):
                self.result_table.setItem(i, column, QTableWidgetItem(
                    "" if value is None else str(value)))
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
