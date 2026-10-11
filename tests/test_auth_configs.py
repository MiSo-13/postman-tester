"""Project-scoped authentication configuration tests."""
import json
from unittest.mock import patch

import httpx
import pytest

from app.storage import Storage
from app.user_auth import (
    DEFAULT_LOGIN_CONFIGS, admin_login, user_login, validate_login_config,
)


def test_config_persists_per_project(tmp_path):
    db = Storage(tmp_path)
    first, second = db.create_project("first"), db.create_project("second")
    config = {"endpoint": "/custom/session", "identifier_key": "account",
              "password_key": "secret"}
    db.save_auth_config(first, "USER", config)
    reopened = Storage(tmp_path)
    assert reopened.get_auth_config(first, "USER") == config
    assert reopened.get_auth_config(second, "USER") is None
    assert reopened.get_auth_config(first, "ADMIN") is None


@pytest.mark.parametrize("endpoint", ["http://evil.test/login", "//evil.test", "/x?redirect=y",
                                       "/x#fragment", "auth/login", "/x\\nattack"])
def test_config_rejects_invalid_paths(endpoint):
    with pytest.raises(ValueError):
        validate_login_config({"endpoint": endpoint, "identifier_key": "id",
                               "password_key": "pw"})


def test_custom_user_login_payload():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={"success": True, "data": {"accessToken": "abc"}})
    config = {"endpoint": "/session/login", "identifier_key": "loginId",
              "password_key": "passcode"}
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handle))):
        assert user_login("http://local.test", "alice", "pw", config=config) == "abc"
    assert requests[0].url.path == "/session/login"
    assert json.loads(requests[0].content) == {"loginId": "alice", "passcode": "pw"}


def test_defaults_remain_compatible():
    assert DEFAULT_LOGIN_CONFIGS["USER"]["endpoint"] == "/api/auth/login"
    assert DEFAULT_LOGIN_CONFIGS["ADMIN"]["endpoint"] == "/api/backoffice/auth/login"
