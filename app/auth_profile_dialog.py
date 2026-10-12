"""Per-project authentication setup dialog, credentials only kept in memory."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QComboBox,
    QLineEdit, QDialogButtonBox, QPushButton, QMessageBox, QLabel)
from .user_auth import validate_login_config, login_tokens
from .auth_profile import endpoint_login_choices, validate_profile_options


class AuthProfileDialog(QDialog):
    def __init__(self, profile, endpoints, config, options, credentials, base_url,
                 timeout, verify_ssl, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.base_url = base_url
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.setWindowTitle(f"{profile} 인증 프로필 설정")
        self.resize(620, 360)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Collection 로그인 API를 선택하고 사용할 계정을 입력하세요. 비밀번호는 저장되지 않습니다."))
        form = QFormLayout()
        self.endpoint = QComboBox()
        self.endpoint.setEditable(True)
        self.endpoint.addItem("(직접 경로 입력)", "")
        for name, path in endpoint_login_choices(endpoints):
            self.endpoint.addItem(f"POST {path} — {name}", path)
        selected = self.endpoint.findData(config["endpoint"])
        if selected >= 0:
            self.endpoint.setCurrentIndex(selected)
        else:
            self.endpoint.setEditText(config["endpoint"])
        form.addRow("로그인 API", self.endpoint)
        self.identifier_key = QLineEdit(config["identifier_key"])
        self.password_key = QLineEdit(config["password_key"])
        form.addRow("ID 요청 필드명", self.identifier_key)
        form.addRow("비밀번호 요청 필드명", self.password_key)
        self.identifier = QLineEdit(credentials[0] if credentials else "")
        self.password = QLineEdit(credentials[1] if credentials else "")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("로그인 ID", self.identifier)
        form.addRow("비밀번호", self.password)
        self.access_path = QLineEdit(options.get("access_path", "data.accessToken"))
        self.refresh_path = QLineEdit(options.get("refresh_path", "data.refreshToken"))
        form.addRow("Access Token 응답 경로", self.access_path)
        form.addRow("Refresh Token 응답 경로", self.refresh_path)
        layout.addLayout(form)
        self.test_button = QPushButton("로그인 연결 테스트")
        self.test_button.clicked.connect(self.test_login)
        layout.addWidget(self.test_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.config = None
        self.options = None
        self.credentials = None

    def values(self):
        route = self.endpoint.currentData()
        if not route or self.endpoint.currentText() != self.endpoint.itemText(self.endpoint.currentIndex()):
            route = self.endpoint.currentText()
        config = validate_login_config({
            "endpoint": route, "identifier_key": self.identifier_key.text(),
            "password_key": self.password_key.text()})
        options = validate_profile_options({
            "access_path": self.access_path.text(),
            "refresh_path": self.refresh_path.text()})
        return config, options, (self.identifier.text(), self.password.text())

    def test_login(self):
        try:
            config, options, credentials = self.values()
            login_tokens(self.profile, self.base_url, *credentials, config=config,
                         token_paths=options, timeout=self.timeout,
                         verify_ssl=self.verify_ssl)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "로그인 테스트 실패", str(exc))
            return
        QMessageBox.information(self, "로그인 테스트 성공", "Access Token을 확인했습니다. 토큰은 저장하지 않습니다.")

    def accept(self):
        try:
            self.config, self.options, self.credentials = self.values()
        except ValueError as exc:
            QMessageBox.warning(self, "인증 설정 오류", str(exc))
            return
        super().accept()
