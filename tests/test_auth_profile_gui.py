"""Authentication profile GUI and configurable token path regression tests."""
from unittest.mock import patch
import httpx
import pytest
from app.auth_profile import validate_profile_options, endpoint_login_choices
from app.storage import Storage
from app.user_auth import login_tokens, refresh_tokens


def test_profile_options_are_validated_and_persisted_without_credentials(tmp_path):
    storage = Storage(tmp_path)
    project = storage.create_project("demo")
    options = {"access_path": "payload.tokens[0].access",
               "refresh_path": "payload.tokens[0].refresh"}
    storage.save_auth_profile_options(project, "USER", options)
    assert storage.get_auth_profile_options(project, "USER") == options
    storage.save_auth_config(project, "USER", {
        "endpoint": "/custom/login", "identifier_key": "email", "password_key": "password"})
    assert "password-secret" not in storage.db_path.read_bytes().decode("utf-8", errors="ignore")
    with pytest.raises(ValueError):
        storage.save_auth_profile_options(project, "USER", {"access_path": "bad[*]"})


def test_custom_token_paths_used_for_login_and_refresh():
    def handler(request):
        if request.url.path == "/custom/login":
            assert request.read().decode().find("password") >= 0
        return httpx.Response(200, json={"success": True,
            "payload": {"tokens": [{"access": "Bearer access123",
                                     "refresh": "Bearer refresh123"}]},
            "data": {}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    with patch("app.user_auth.httpx.Client", return_value=client):
        paths = {"access_path": "payload.tokens[0].access",
                 "refresh_path": "payload.tokens[0].refresh"}
        config = {"endpoint": "/custom/login",
                  "identifier_key": "email", "password_key": "password"}
        assert login_tokens("USER", "https://example.test", "id", "pw",
                            config=config, token_paths=paths) == ("access123", "refresh123")
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        assert refresh_tokens("USER", "https://example.test", "refresh123",
                              token_paths=paths)[0] == "access123"


def test_auth_gui_selects_collection_request_and_keeps_password_in_memory():
    from types import SimpleNamespace
    from PyQt6.QtWidgets import QApplication
    from app.auth_profile_dialog import AuthProfileDialog
    app = QApplication.instance() or QApplication([])
    endpoints = [SimpleNamespace(method="POST", name="로그인", url="{{baseUrl}}/custom/login")]
    config = {"endpoint": "/custom/login", "identifier_key": "email", "password_key": "pw"}
    dialog = AuthProfileDialog("USER", endpoints, config, {}, ("id", "secret"),
                               "https://example.test", 10, True)
    updated, paths, credentials = dialog.values()
    assert updated == config
    assert paths["access_path"] == "data.accessToken"
    assert credentials == ("id", "secret")
    assert app is not None
