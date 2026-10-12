"""Initial functional PyQt6 shell with import, safe test runs and persistent history."""
import json
import sys
import shutil
import httpx
from threading import Event
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTreeWidget, QTreeWidgetItem, QTextEdit, QLabel,
    QComboBox, QFileDialog, QMessageBox, QInputDialog, QSplitter,
    QTabWidget, QStackedWidget, QListWidget, QListWidgetItem, QCheckBox, QLineEdit, QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem, QAbstractItemView, QProgressBar
)

from .settings import Settings
from .storage import Storage
from .postman import parse_collection, parse_environment, preview_body, preview_response, Endpoint
from .templates import save_examples
from .runner import execute
from .reports import export_reports
from .user_auth import login_tokens, refresh_tokens, needs_user_token, needs_admin_token, LoginError, DEFAULT_LOGIN_CONFIGS
from .postman_auth_config import clean_environment, discover_auth
from .auth_profile_dialog import AuthProfileDialog
from .ai_test_dialog import AITestDialog
from .ai_adaptive import choose_next, move_next
from .ai_usage import usage_summary
from .request_overrides import endpoint_key, validate_raw_json
from .scenarios import resolve_steps, validate_steps, should_stop
from .retry import retry_candidates
from .run_comparison import compare_runs
from .comparison_reports import export_comparison, summarize
from .history_dashboard import build_dashboard
from .trend_chart import TrendChart
from .retry_policy import RetryPolicy, execute_with_retries
from .themes import THEMES, validate_theme, apply_theme
from .performance_reports import export_performance_report
from .assertion_editor import AssertionRuleEditor
from .response_field_dialog import ResponseFieldRuleDialog
from .assertions import validate_rules
from .ui_components import ProjectHeader, NavigationSidebar, EndpointExplorer
from .dashboard_widgets import DashboardMetrics
from .developer_style import developer_stylesheet
from .workspace_pages import ProjectHome, WorkspaceOverview


class RunWorker(QThread):
    progress = pyqtSignal(str, str)
    finished_run = pyqtSignal(str)
    step_result = pyqtSignal(int, int, str, str)
    response_preview = pyqtSignal(str, int, str)
    ai_decision = pyqtSignal(str)

    def __init__(self, storage, run_id, endpoints, variables, settings, body_overrides, user_credentials=None, admin_credentials=None, auth_configs=None, response_rules=None, extraction_rules=None, stop_on_failure=False, retry_policy=None, refresh_paths=None, token_paths=None, adaptive_ai=None):
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
        self.cancel_event = Event()
        self.retry_policy = retry_policy or RetryPolicy()
        self.refresh_paths = refresh_paths or {}
        self.token_paths = token_paths or {}
        self.adaptive_ai = adaptive_ai

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        status = "COMPLETED"
        try:
            sessions = {"USER": None, "ADMIN": None}
            profiles = (
                ("USER", self.user_credentials, needs_user_token),
                ("ADMIN", self.admin_credentials, needs_admin_token),
            )
            for profile, credentials, checker in profiles:
                if self.cancel_event.is_set():
                    status = "CANCELLED"
                    return
                if credentials and any(checker(e) for _, e in self.endpoints):
                    try:
                        sessions[profile] = login_tokens(
                            profile, self.variables.get("baseUrl", ""), *credentials,
                            timeout=self.settings.values["default_timeout_seconds"],
                            verify_ssl=self.settings.values["verify_ssl"],
                            config=self.auth_configs.get(profile),
                            token_paths=self.token_paths.get(profile))
                        self.progress.emit(f"{profile} 로그인", "PASS")
                        if self.cancel_event.is_set():
                            status = "CANCELLED"
                            return
                    except LoginError as exc:
                        self.progress.emit(f"{profile} 로그인", f"ERROR: {exc}")
                        status = "ERROR"
                        return
            with httpx.Client(timeout=self.settings.values["default_timeout_seconds"],
                             verify=self.settings.values["verify_ssl"],
                             follow_redirects=False) as client:
                pending = list(self.endpoints)
                executed = []
                ai_calls = 0
                step_index = 0
                while pending:
                    step_index += 1
                    key, endpoint = pending.pop(0)
                    if self.cancel_event.is_set():
                        status = "CANCELLED"
                        break
                    selected_profile = ("USER" if needs_user_token(endpoint) else
                                        "ADMIN" if needs_admin_token(endpoint) else None)
                    user_token = sessions["USER"][0] if sessions["USER"] else None
                    admin_token = sessions["ADMIN"][0] if sessions["ADMIN"] else None
                    def request_once():
                        # Single request builder reused for normal run and post-refresh replay.
                        return execute(
                            endpoint, self.variables,
                            timeout=self.settings.values["default_timeout_seconds"],
                            verify_ssl=self.settings.values["verify_ssl"],
                            allow_writes=self.settings.values["dangerous_methods_enabled"],
                            raw_body_override=self.body_overrides.get(key),
                            user_access_token=sessions["USER"][0] if sessions["USER"] else None,
                            admin_access_token=sessions["ADMIN"][0] if sessions["ADMIN"] else None,
                            file_root=self.settings.root / self.settings.values["file_root"],
                            assertions=self.response_rules.get(key, []),
                            extraction_rules=self.extraction_rules.get(key, []),
                            captured_variables=self.variables,
                            client=client,
                            preview_callback=lambda text, row=step_index - 1:
                                self.response_preview.emit(self.run_id, row, text))
                    attempts = []
                    result = execute_with_retries(
                        request_once, endpoint, self.retry_policy,
                        cancelled=self.cancel_event.is_set,
                        on_attempt=attempts.append)
                    if result is None:
                        status = "CANCELLED"
                        break
                    # Only read-only requests may be automatically replayed after 401.
                    if (not self.cancel_event.is_set() and selected_profile and result.get("http_status") == 401
                            and endpoint.method.upper() in ("GET", "HEAD", "OPTIONS")
                            and sessions[selected_profile] and sessions[selected_profile][1]):
                        try:
                            sessions[selected_profile] = refresh_tokens(
                                selected_profile, self.variables.get("baseUrl", ""),
                                sessions[selected_profile][1],
                                timeout=self.settings.values["default_timeout_seconds"],
                                verify_ssl=self.settings.values["verify_ssl"],
                                endpoint=self.refresh_paths.get(selected_profile),
                                token_paths=self.token_paths.get(selected_profile))
                            self.progress.emit(f"{selected_profile} 토큰 갱신", "PASS")
                            user_token = sessions["USER"][0] if sessions["USER"] else None
                            admin_token = sessions["ADMIN"][0] if sessions["ADMIN"] else None
                            result = request_once()
                        except LoginError as exc:
                            self.progress.emit(f"{selected_profile} 토큰 갱신", f"ERROR: {exc}")
                            result["status"] = "ERROR"
                            result["detail"] = f"{selected_profile} 토큰 갱신 실패"
                    # Persist the in-flight request result, then honor cancellation.
                    self.storage.add_result(
                        self.run_id, endpoint.name, endpoint.method, endpoint.url,
                        **result, retry_count=max(0, len(attempts) - 1))
                    self.progress.emit(endpoint.name, result["status"])
                    self.step_result.emit(step_index, len(self.endpoints), endpoint.name, result["status"])
                    if self.cancel_event.is_set():
                        status = "CANCELLED"
                        break
                    executed.append({"status": result["status"],
                                     "http_status": result.get("http_status"),
                                     "method": endpoint.method})
                    # The explicit stop-on-failure policy takes precedence over AI reordering.
                    if should_stop(result["status"], self.stop_on_failure):
                        status = "STOPPED"
                        break
                    if (self.adaptive_ai and pending and ai_calls < self.adaptive_ai["max_calls"]
                            and result["status"] in ("FAIL", "ERROR", "BLOCKED")
                            and not self.cancel_event.is_set()):
                        ai_calls += 1
                        try:
                            decision, usage = choose_next(
                                self.adaptive_ai["key"], self.adaptive_ai["model"],
                                executed, pending)
                            self.ai_decision.emit(
                                f"AI 재계획 {ai_calls}/{self.adaptive_ai['max_calls']}: "
                                f"{decision['action']} · {decision['reason']} · "
                                + usage_summary(usage))
                            if decision["action"] == "stop":
                                status = "STOPPED"
                                break
                            pending = move_next(pending, decision["next_id"])
                        except ValueError:
                            self.ai_decision.emit("AI 재계획 불가: 기존 승인 순서대로 계속합니다.")
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
        self.system_palette = QApplication.palette()
        try:
            self.theme = validate_theme(self.settings.values["theme"])
        except ValueError:
            self.theme = "system"
        apply_theme(QApplication.instance(), self.theme, self.system_palette)
        self.storage = Storage(self.settings.data_path())
        self.endpoints = []
        self.environment = {}
        self.session_credentials = {}
        self.auth_discovered = {}
        self.refresh_discovered = {}
        self.endpoint_keys = []
        self.selected_endpoint_index = None
        self.response_previews = {}
        self.active_preview_run = None
        self.setWindowTitle("Postman Tester")
        self.resize(1150, 760)
        self.build_ui()
        QApplication.instance().setStyleSheet(developer_stylesheet(self.theme))
        self.body_editor.setEnabled(False)
        self.body_save.setEnabled(False)
        self.body_reset.setEnabled(False)
        self.refresh_projects()

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = ProjectHeader()
        self.projects = self.header.projects
        self.projects.currentIndexChanged.connect(self.project_changed)
        self.theme_selector = self.header.theme_selector
        for label, key in (("시스템", "system"), ("라이트", "light"), ("다크", "dark")):
            self.theme_selector.addItem(label, key)
        self.theme_selector.setCurrentIndex(self.theme_selector.findData(self.theme))
        self.theme_selector.currentIndexChanged.connect(self.change_theme)
        layout.addWidget(self.header)

        workspace = QHBoxLayout()
        workspace.setContentsMargins(0, 0, 0, 0)
        workspace.setSpacing(0)
        self.project_buttons = []
        navigation = [
            ("화면", [
                ("홈", lambda: self.show_workspace("home")),
                ("API 탐색", lambda: self.show_workspace("api")),
                ("실행 이력", lambda: self.show_workspace("history"))]),
            ("워크스페이스", [
                ("새 프로젝트", self.add_project),
                ("프로젝트 삭제", self.delete_project),
                ("Collection Import", self.import_collection),
                ("Environment Import", self.import_environment),
                ("예제 JSON 내려받기", self.download_examples)]),
            ("테스트", [
                ("테스트 실행", self.start_run),
                ("AI 테스트 계획", self.ai_test_plan),
                ("시나리오 관리", self.manage_scenarios)]),
            ("설정", [
                ("로그인 설정", self.configure_logins),
                ("응답 검증 규칙", self.configure_assertions),
                ("응답 변수 추출", self.configure_extractions)]),
            ("분석", [
                ("실행 결과 대시보드", self.show_dashboard),
                ("실행 회차 비교", self.compare_run_history)]),
        ]
        self.sidebar = NavigationSidebar(navigation)
        for label, button in self.sidebar.buttons.items():
            if label not in ("새 프로젝트", "예제 JSON 내려받기", "홈", "API 탐색", "실행 이력"):
                self.project_buttons.append(button)
        workspace.addWidget(self.sidebar)
        main_panel = QWidget()
        main_column = QVBoxLayout(main_panel)
        main_column.setContentsMargins(12, 8, 12, 8)
        workspace.addWidget(main_panel, 1)
        layout.addLayout(workspace, 1)
        self.workspace_stack = QStackedWidget()
        main_column.addWidget(self.workspace_stack, 1)
        self.home_page = ProjectHome(self.add_project, self.import_collection, self.import_environment)
        self.workspace_stack.addWidget(self.home_page)
        self.api_page = QWidget()
        api_column = QVBoxLayout(self.api_page)
        api_column.setContentsMargins(0, 0, 0, 0)
        self.workspace_stack.addWidget(self.api_page)
        self.history_page = WorkspaceOverview("실행 이력", "이전 실행 기록과 리포트, 운영 대시보드를 확인하세요.", [
            ("이전 실행 보기", lambda: self.open_api_tab("이전 실행")),
            ("결과 상세 보기", lambda: self.open_api_tab("실행 결과 상세")),
            ("운영 대시보드", self.show_dashboard),
            ("실행 회차 비교", self.compare_run_history)])
        self.workspace_stack.addWidget(self.history_page)
        self.workspace_tabs = None
        run_controls = QHBoxLayout()
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 100)
        self.run_progress.setValue(0)
        self.cancel_button = QPushButton("실행 취소")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_run)
        run_controls.addWidget(self.run_progress)
        run_controls.addWidget(self.cancel_button)
        api_column.addLayout(run_controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.explorer = EndpointExplorer()
        self.tree = self.explorer.tree
        self.tree.currentItemChanged.connect(self.show_endpoint)
        splitter.addWidget(self.explorer)

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
        self.response_inspector = QTextEdit()
        self.response_inspector.setReadOnly(True)
        self.response_inspector.setPlainText("실행 결과를 선택하면 응답 미리보기를 확인할 수 있습니다.")
        self.result_table.itemSelectionChanged.connect(self.show_selected_response)
        self.create_assertion_button = QPushButton("응답 필드에서 검증 규칙 만들기")
        self.create_assertion_button.clicked.connect(self.create_assertion_from_response)
        self.retry_button = QPushButton("선택한 실패 읽기 API 재실행")
        self.retry_button.clicked.connect(self.retry_failed)
        results_panel = QWidget()
        results_layout = QVBoxLayout(results_panel)
        results_layout.addWidget(self.result_table)
        results_layout.addWidget(QLabel("응답 미리보기 (메모리 전용 · 문자열 마스킹)"))
        results_layout.addWidget(self.response_inspector)
        results_layout.addWidget(self.create_assertion_button)
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
        self.workspace_tabs = tabs
        splitter.addWidget(tabs)
        splitter.setSizes([420, 720])
        api_column.addWidget(splitter)
        self.show_workspace("home")
        self.statusBar().showMessage("Collection을 가져와 시작하세요.")

    def show_workspace(self, page):
        lookup = {"home": 0, "api": 1, "history": 2}
        if page not in lookup:
            raise ValueError("지원하지 않는 작업 화면입니다.")
        if page != "home" and not self.current_project():
            page = "home"
        self.workspace_stack.setCurrentIndex(lookup[page])
        labels = {"home": "홈", "api": "API 탐색", "history": "실행 이력"}
        for label, button in self.sidebar.buttons.items():
            if label in labels.values():
                button.setProperty("active", label == labels[page])
                button.style().unpolish(button)
                button.style().polish(button)

    def open_api_tab(self, tab_label):
        for index in range(self.workspace_tabs.count()):
            if self.workspace_tabs.tabText(index) == tab_label:
                self.workspace_tabs.setCurrentIndex(index)
                self.show_workspace("api")
                return
        raise ValueError("없는 작업 탭입니다.")

    def change_theme(self, _=None):
        theme = self.theme_selector.currentData()
        if theme is None or theme == self.theme:
            return
        validate_theme(theme)
        apply_theme(QApplication.instance(), theme, self.system_palette)
        QApplication.instance().setStyleSheet(developer_stylesheet(theme))
        self.theme = theme
        self.settings.set("theme", theme)
        self.statusBar().showMessage(f"테마가 변경되었습니다: {self.theme_selector.currentText()}")

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

    def delete_project(self):
        project = self.current_project()
        if not project:
            return
        if hasattr(self, "worker") and self.worker.isRunning():
            QMessageBox.warning(self, "삭제 불가", "테스트 실행이 종료된 후 프로젝트를 삭제하세요.")
            return
        name = self.projects.currentText()
        confirmation, ok = QInputDialog.getText(
            self, "프로젝트 영구 삭제",
            f"'{name}' 프로젝트의 Collection, 설정, 테스트 결과 및 보고서를 삭제합니다.\\n"
            f"확인하려면 프로젝트 이름 '{name}'을(를) 입력하세요.")
        if not ok or confirmation != name:
            return
        try:
            run_ids = self.storage.delete_project(project)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "프로젝트 삭제 실패", str(exc))
            return
        # Only delete generated per-run folders inside our managed reports root.
        reports_root = (self.settings.data_path() / "reports").resolve()
        failures = []
        for run_id in run_ids:
            folder = (reports_root / run_id).resolve()
            if folder.parent != reports_root:
                continue
            try:
                if folder.is_dir():
                    shutil.rmtree(folder)
            except OSError as exc:
                failures.append(str(exc))
        self.session_credentials.clear()
        self.settings.set("last_project_id", None)
        self.refresh_projects()
        if failures:
            QMessageBox.warning(self, "일부 보고서 정리 실패",
                                "프로젝트 데이터는 삭제되었지만 일부 보고서 파일이 남았습니다.\\n"
                                + "\\n".join(failures[:3]))
        else:
            self.statusBar().showMessage(f"프로젝트 '{name}' 삭제 완료")

    def project_changed(self, *_):
        project = self.current_project()
        # No modal warning is necessary when no project exists.
        # Keep these actions disabled until a project is selected.
        for button in self.project_buttons:
            button.setEnabled(bool(project))
        self.home_page.set_project_available(bool(project))
        self.sidebar.buttons["API 탐색"].setEnabled(bool(project))
        self.sidebar.buttons["실행 이력"].setEnabled(bool(project))
        self.show_workspace("api" if project else "home")
        self.tree.clear()
        self.endpoints = []
        self.endpoint_keys = []
        self.selected_endpoint_index = None
        self.environment = {}
        self.session_credentials.clear()
        self.auth_discovered = {}
        self.refresh_discovered = {}
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
            _, self.environment = clean_environment(doc)
        saved_base_url = self.storage.get_project_base_url(project)
        if saved_base_url:
            self.environment["baseUrl"] = saved_base_url
        self.refresh_history()

    def load_collection_document(self, document):
        from .postman import endpoints_from_document
        self.endpoints = endpoints_from_document(document)
        self.auth_discovered, self.refresh_discovered = discover_auth(self.endpoints)
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
            item.setData(0, Qt.ItemDataRole.UserRole + 1, endpoint.url)
            parent.addChild(item)
        self.tree.expandAll()
        self.explorer.apply_filter(self.explorer.search.text())
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
            document = json.loads(Path(filename).read_text(encoding="utf-8-sig"))
            _, self.environment = clean_environment(document)
            self.storage.save_import(self.current_project(), "environment", Path(filename).name, document)
            self.statusBar().showMessage(f"변수 {len(self.environment)}개 로드 완료")
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Import 오류", str(exc))

    def configure_logins(self):
        project = self.current_project()
        if not project:
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 먼저 선택하세요.")
            return
        for profile in ("USER", "ADMIN"):
            config = (self.storage.get_auth_config(project, profile)
                      or self.auth_discovered.get(profile)
                      or DEFAULT_LOGIN_CONFIGS[profile])
            options = self.storage.get_auth_profile_options(project, profile)
            dialog = AuthProfileDialog(
                profile, self.endpoints, config, options,
                self.session_credentials.get(profile),
                self.storage.get_project_base_url(project) or self.environment.get("baseUrl", ""),
                self.settings.values["default_timeout_seconds"],
                self.settings.values["verify_ssl"], self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self.storage.save_project_base_url(project, dialog.base_url)
            self.environment["baseUrl"] = dialog.base_url
            self.storage.save_auth_config(project, profile, dialog.config)
            self.storage.save_auth_profile_options(project, profile, dialog.options)
            self.session_credentials[profile] = dialog.credentials
        self.statusBar().showMessage("인증 프로필 설정이 저장되었습니다. 비밀번호는 세션에만 유지됩니다.")

    def configure_assertions(self):
        index = self.selected_endpoint_index
        if index is None or not self.current_project():
            QMessageBox.warning(self, "API 선택 필요", "검증할 API를 먼저 선택하세요.")
            return
        key = self.endpoint_keys[index]
        existing = self.storage.get_response_assertions(self.current_project(), key)
        try:
            dialog = AssertionRuleEditor(existing, self)
        except ValueError as exc:
            QMessageBox.warning(self, "규칙 오류", str(exc))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.storage.save_response_assertions(self.current_project(), key, dialog.rules)
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

    def cancel_run(self):
        if hasattr(self, "worker") and self.worker.isRunning():
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("취소 요청됨: 현재 HTTP 요청 종료 후 중단")

    def ai_test_plan(self):
        if not self.current_project() or not self.endpoints:
            QMessageBox.warning(self, "Collection 필요", "먼저 Collection을 업로드하세요.")
            return
        if hasattr(self, "worker") and self.worker.isRunning():
            QMessageBox.warning(self, "실행 중", "기존 테스트가 끝난 뒤 AI 모드를 실행하세요.")
            return
        dialog = AITestDialog(self.endpoint_keys, self.endpoints, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            ordered = resolve_steps(dialog.selected_keys, self.endpoint_keys, self.endpoints)
        except ValueError as exc:
            QMessageBox.warning(self, "계획 오류", str(exc))
            return
        self.start_run(planned_endpoints=ordered, adaptive_ai={
            "key": dialog.key.text(), "model": dialog.model.text(),
            "max_calls": dialog.adaptive_calls.value()})

    def start_run(self, checked=False, *, retry_endpoints=None, planned_endpoints=None, adaptive_ai=None):
        if hasattr(self, "worker") and self.worker.isRunning():
            QMessageBox.warning(self, "실행 중", "이미 실행 중인 작업이 있습니다.")
            return
        if self.body_message.text() == "저장되지 않은 수정사항":
            QMessageBox.warning(
                self, "저장되지 않은 JSON",
                "JSON Body 편집 내용이 저장되지 않았습니다. 먼저 'JSON 수정 저장'을 눌러주세요.")
            return
        if not self.current_project() or not self.endpoints:
            QMessageBox.warning(self, "실행 불가", "프로젝트와 Collection을 선택하세요.")
            return
        if planned_endpoints is not None:
            endpoints = planned_endpoints
            scenario_name = "AI 승인 테스트"
        elif retry_endpoints is not None:
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
        attempts, ok = QInputDialog.getInt(
            self, "읽기 API 재시도", "일시적인 장애 시 재시도 횟수 (0~5)", 0, 0, 5)
        if not ok:
            return
        delay = 0.0
        if attempts:
            delay, ok = QInputDialog.getDouble(
                self, "재시도 간격", "재시도 사이 대기 시간(초)", 0.5, 0, 10, 1)
            if not ok:
                return
        retry_policy = RetryPolicy(attempts, delay)
        user_credentials = self.session_credentials.get("USER")
        if not user_credentials and any(needs_user_token(e) for _, e in endpoints):
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
        admin_credentials = self.session_credentials.get("ADMIN")
        if not admin_credentials and any(needs_admin_token(e) for _, e in endpoints):
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
                     or self.auth_discovered.get(profile)
                     or DEFAULT_LOGIN_CONFIGS[profile]
            for profile in ("USER", "ADMIN")
        }
        token_paths = {profile: self.storage.get_auth_profile_options(self.current_project(), profile)
                       for profile in ("USER", "ADMIN")}
        response_rules = {
            key: self.storage.get_response_assertions(self.current_project(), key)
            for key, _ in endpoints
        }
        extraction_rules = {
            key: self.storage.get_response_extractions(self.current_project(), key)
            for key, _ in endpoints
        }
        run_id = self.storage.create_run(self.current_project(), scenario_name or '기본 실행')
        self.response_previews.clear()
        self.active_preview_run = run_id
        self.log_text.append(f'Run ID: {run_id}')
        self.worker = RunWorker(
            self.storage, run_id, endpoints, self.environment.copy(), self.settings,
            body_overrides, user_credentials, admin_credentials, auth_configs, response_rules, extraction_rules,
            stop_on_failure=stop_on_failure, retry_policy=retry_policy,
            refresh_paths=self.refresh_discovered, token_paths=token_paths,
            adaptive_ai=adaptive_ai)
        self.worker.progress.connect(lambda name, state: self.log_text.append(f"[{state}] {name}"))
        self.worker.step_result.connect(lambda i, total, name, state: (
            self.run_progress.setValue(round(i / total * 100)),
            self.log_text.append(f"단계 {i}/{total}: [{state}] {name}")))
        self.worker.response_preview.connect(self.record_response_preview)
        self.worker.ai_decision.connect(lambda message: self.log_text.append(message))
        self.worker.finished_run.connect(self.run_finished)
        self.run_progress.setValue(0)
        self.cancel_button.setEnabled(True)
        self.worker.start()
        self.statusBar().showMessage("테스트 실행 중")

    def run_finished(self, run_id):
        self.cancel_button.setEnabled(False)
        try:
            output = self.settings.data_path() / "reports" / run_id
            paths = export_reports(self.storage, run_id, output)
            paths.extend(export_performance_report(self.storage, run_id, output))
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

    def show_dashboard(self):
        project = self.current_project()
        if not project:
            QMessageBox.warning(self, "프로젝트 필요", "프로젝트를 선택하세요.")
            return
        runs = self.storage.runs(project)
        completed = [run for run in runs if run["status"] != "PENDING"][:30]
        if not completed:
            QMessageBox.information(self, "실행 이력 없음", "완료된 실행 이력이 없습니다.")
            return
        dashboard = build_dashboard(
            completed, self.storage.results_for_runs(project, [run["id"] for run in completed]))
        dialog = QDialog(self)
        dialog.setWindowTitle("실행 결과 대시보드 — 최근 30회")
        dialog.resize(1020, 680)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("운영 대시보드  /  최근 완료된 30회 실행"))
        layout.addWidget(DashboardMetrics(dashboard, dialog))
        layout.addWidget(TrendChart(
            [item["failure_rate"] for item in dashboard["timeline"]],
            "실행 회차별 실패율 (%)", "%", dialog))
        layout.addWidget(TrendChart(
            [item["avg_ms"] for item in dashboard["timeline"]],
            "실행 회차별 평균 응답 시간 (ms)", "ms", dialog))
        tabs = QTabWidget()
        trend = QTableWidget(len(dashboard["timeline"]), 7)
        trend.setHorizontalHeaderLabels(
            ["실행 시각", "회차명", "PASS", "실패", "SKIPPED", "실패율(%)", "평균(ms)"])
        trend.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, run in enumerate(dashboard["timeline"]):
            values = [run["started_at"], run["name"], run["pass"], run["fail"],
                      run["skipped"], run["failure_rate"], run["avg_ms"]]
            for j, value in enumerate(values):
                trend.setItem(i, j, QTableWidgetItem("—" if value is None else str(value)))
        tabs.addTab(trend, "회차별 추이")
        apis = QTableWidget(len(dashboard["apis"]), 8)
        apis.setHorizontalHeaderLabels(
            ["API", "Method", "PASS", "실패", "SKIPPED", "실패율(%)", "평균(ms)", "최근 결과"])
        apis.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for i, api in enumerate(dashboard["apis"]):
            values = [api["name"], api["method"], api["pass"], api["fail"],
                      api["skipped"], api["failure_rate"], api["avg_ms"], api["latest"]]
            for j, value in enumerate(values):
                apis.setItem(i, j, QTableWidgetItem("—" if value is None else str(value)))
        tabs.addTab(apis, "API별 실패율·응답시간")
        layout.addWidget(tabs)
        layout.addWidget(QLabel("실패율 = (FAIL + ERROR + BLOCKED) / (PASS + FAIL + ERROR + BLOCKED). SKIPPED 제외."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

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
        summary = summarize(changes)
        layout.addWidget(QLabel(" | ".join(
            f"{k}: {v}" for k, v in summary.items()) or "비교 대상 없음"))
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
        export_button = QPushButton("비교 보고서 HTML·Excel 저장")
        def export_selected_comparison():
            directory = QFileDialog.getExistingDirectory(
                dialog, "비교 보고서 저장 위치",
                str(self.settings.data_path() / "reports"))
            if not directory:
                return
            try:
                paths = export_comparison(
                    self.storage, runs[i]["id"], runs[j]["id"], Path(directory))
            except (ValueError, OSError) as exc:
                QMessageBox.warning(dialog, "보고서 저장 실패", str(exc))
                return
            QMessageBox.information(dialog, "저장 완료",
                "저장된 보고서:\\n" + "\\n".join(map(str, paths)))
        export_button.clicked.connect(export_selected_comparison)
        layout.addWidget(export_button)
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

    def create_assertion_from_response(self):
        selected = self.history.currentItem()
        selection = self.result_table.selectionModel()
        rows = selection.selectedRows() if selection else []
        if not selected or len(rows) != 1:
            QMessageBox.warning(self, "결과 선택", "실행 회차와 API 결과 한 행을 선택하세요.")
            return
        run_id = selected.text().split()[-1]
        row = rows[0].row()
        preview = self.response_previews.get(row) if run_id == self.active_preview_run else None
        if not preview:
            QMessageBox.warning(self, "미리보기 없음", "현재 실행의 응답 미리보기가 필요합니다.")
            return
        results = self.storage.results(run_id)
        if row >= len(results):
            return
        item = results[row]
        matches = [i for i, endpoint in enumerate(self.endpoints)
                   if endpoint.name == item["endpoint_name"]
                   and endpoint.method == item["method"]
                   and endpoint.url == item["url"]]
        if len(matches) != 1:
            QMessageBox.warning(self, "API 식별 불가",
                "Collection에서 API를 유일하게 식별할 수 없습니다. 원본 API를 선택해 규칙을 편집하세요.")
            return
        dialog = ResponseFieldRuleDialog(preview, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        key = self.endpoint_keys[matches[0]]
        existing = self.storage.get_response_assertions(self.current_project(), key)
        try:
            suggested = validate_rules([*existing, dialog.rule])
        except ValueError as exc:
            QMessageBox.warning(self, "규칙 제한", str(exc))
            return
        editor = AssertionRuleEditor(suggested, self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self.storage.save_response_assertions(self.current_project(), key, editor.rules)
        except ValueError as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return
        self.statusBar().showMessage("응답에서 생성한 검증 규칙을 저장했습니다.")

    def record_response_preview(self, run_id, row, preview):
        if run_id == self.active_preview_run and 0 <= row < 500:
            self.response_previews[row] = preview
            self.show_selected_response()

    def show_selected_response(self):
        current = self.history.currentItem()
        run_id = current.text().split()[-1] if current else None
        selection = self.result_table.selectionModel()
        indexes = selection.selectedRows() if selection else []
        preview = (self.response_previews.get(indexes[0].row())
                   if run_id == self.active_preview_run and indexes else None)
        self.response_inspector.setPlainText(
            preview if preview else
            "응답 원문은 저장되지 않습니다. 새 실행에서 선택한 API만 미리보기가 제공됩니다.")

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
        self.show_selected_response()
        for report in self.storage.reports(run_id):
            self.report_list.addItem(f"{report['format'].upper()}  {report['file_path']}")


def launch():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()
