"""Original two-file Postman workflow: route detection and non-persistence."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from app.postman_auth_config import clean_environment, discover_auth
from app.storage import Storage
from app.user_auth import refresh_tokens


def endpoint(path, body):
    return SimpleNamespace(method="POST", url="{{baseUrl}}" + path,
        request={"body": {"mode": "raw", "raw": body}})


def test_discover_user_and_admin_auth_from_collection_shapes():
    endpoints = [
        endpoint("/api/auth/login", '{"userEmail":"example", // example only\n"userPassword":"sample"}'),
        endpoint("/api/backoffice/auth/login", '{"adminId":"example","adminPw":"sample"}'),
        endpoint("/api/auth/refresh", '{"refreshToken":"{{userRefreshToken}}"}'),
        endpoint("/api/backoffice/auth/refresh", '{"refreshToken":"{{adminRefreshToken}}"}'),
    ]
    login, refresh = discover_auth(endpoints)
    assert login["USER"] == {"endpoint": "/api/auth/login",
        "identifier_key": "userEmail", "password_key": "userPassword"}
    assert login["ADMIN"]["password_key"] == "adminPw"
    assert refresh == {"USER": "/api/auth/refresh",
                       "ADMIN": "/api/backoffice/auth/refresh"}


def test_environment_secret_values_never_persist_even_when_enabled(tmp_path):
    environment = {"values": [
        {"key": "baseUrl", "value": "http://localhost:8080", "enabled": True},
        {"key": "userAccessToken", "value": "private-token", "type": "default"},
        {"key": "adminRefreshToken", "value": "refresh-secret", "type": "secret"},
        {"key": "privateField", "value": "private-value", "type": "secret"},
    ]}
    cleaned, variables = clean_environment(environment)
    assert variables == {"baseUrl": "http://localhost:8080"}
    assert all(x["value"] == "" for x in cleaned["values"][1:])
    store = Storage(tmp_path)
    project = store.create_project("auth")
    store.save_import(project, "environment", "local.json", environment)
    loaded = store.latest_import(project, "environment")
    for secret in ("private-token", "refresh-secret", "private-value"):
        assert secret not in loaded["content"]
    assert "baseUrl" in loaded["content"]


def test_refresh_accepts_discovered_route():
    requested = []
    def handler(request):
        requested.append(request.url.path)
        assert request.method == "POST"
        return httpx.Response(200, json={"success": True, "data": {
            "accessToken": "Bearer access-2", "refreshToken": "refresh-2"}})
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handler))):
        assert refresh_tokens("USER", "https://example.test", "refresh-1",
                              endpoint="/custom/auth/refresh") == ("access-2", "refresh-2")
    assert requested == ["/custom/auth/refresh"]
