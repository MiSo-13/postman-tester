"""ADMIN authentication isolated from USER credentials and tokens."""
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.user_auth import admin_login, needs_admin_token, LoginError
from app.runner import execute


def admin_endpoint():
    return SimpleNamespace(
        method="GET",
        url="{{baseUrl}}/api/backoffice/users",
        request={"header": [], "auth": {"type": "bearer", "bearer": [
            {"key": "token", "value": "{{adminAccessToken}}"}]}}
    )


def test_admin_login_endpoint_payload_and_token():
    def handler(request):
        assert request.url.path == "/api/backoffice/auth/login"
        assert request.method == "POST"
        assert __import__("json").loads(request.content) == {
            "adminId": "admin", "adminPw": "super-secret"}
        return httpx.Response(200, json={
            "success": True, "data": {"accessToken": "Bearer admin-token"}})

    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handler))):
        assert admin_login("http://example.test", "admin", "super-secret") == "admin-token"


def test_admin_bearer_is_isolated_from_user():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"success": True})
    api = admin_endpoint()
    assert needs_admin_token(api)
    assert execute(api, {"baseUrl": "http://example.test"},
                   user_access_token="user-only")["status"] == "BLOCKED"
    with patch("app.runner.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handler))):
        result = execute(api, {"baseUrl": "http://example.test"},
                         user_access_token="user-only", admin_access_token="admin-token")
    assert result["status"] == "PASS"
    assert requests[0].headers["authorization"] == "Bearer admin-token"


def test_admin_login_error_is_sanitized():
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(403, text="secret-value")))):
        with pytest.raises(LoginError) as exc:
            admin_login("http://example.test", "admin", "secret-password")
    assert "secret-password" not in str(exc.value)
    assert "secret-value" not in str(exc.value)
