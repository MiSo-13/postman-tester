"""Login dialog must handle network/login failures without aborting the Qt process."""
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.auth_base_url import validate_base_url
from app.auth_profile_dialog import AuthProfileDialog
from app.storage import Storage
from app.user_auth import LoginError


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("value", [
    "", "localhost:8080", "ftp://localhost", "http://localhost/login",
    "http://user:pass@localhost", "http://localhost:bad", "http://localhost?q=x"
])
def test_invalid_base_url_rejected(value):
    with pytest.raises(ValueError):
        validate_base_url(value)


def test_base_url_project_persistence(tmp_path):
    storage = Storage(tmp_path)
    first = storage.create_project("first")
    second = storage.create_project("second")
    assert storage.get_project_base_url(first) is None
    storage.save_project_base_url(first, "  http://localhost:8080/  ")
    assert storage.get_project_base_url(first) == "http://localhost:8080"
    assert storage.get_project_base_url(second) is None
    assert Storage(tmp_path).get_project_base_url(first) == "http://localhost:8080"


def test_login_error_shows_warning_without_escaping_slot(app):
    dialog = AuthProfileDialog(
        "USER", [], {"endpoint": "/api/auth/login", "identifier_key": "userEmail",
                     "password_key": "userPassword"}, {}, None, "http://localhost:8080", 1, True)
    dialog.identifier.setText("sample@example.com")
    dialog.password.setText("wrong")
    messages = []
    try:
        with patch("app.auth_profile_dialog.login_tokens", side_effect=LoginError("HTTP 401")) as login, \\
             patch.object(QMessageBox, "warning", side_effect=lambda *args: messages.append(args[2])):
            dialog.test_login()
        assert len(messages) == 1
        assert "HTTP 401" in messages[0]
        assert login.call_args.args[1] == "http://localhost:8080"
    finally:
        dialog.close()


def test_dialog_accept_saves_selected_base_url(app):
    dialog = AuthProfileDialog(
        "USER", [], {"endpoint": "/api/auth/login", "identifier_key": "userEmail",
                     "password_key": "userPassword"}, {}, None, "", 1, True)
    try:
        dialog.base_url_input.setText("http://127.0.0.1:8081")
        dialog.accept()
        assert dialog.base_url == "http://127.0.0.1:8081"
    finally:
        dialog.close()
