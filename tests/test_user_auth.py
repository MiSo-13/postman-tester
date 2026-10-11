"""USER authentication tests using local HTTPX mock transport."""
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.user_auth import LoginError, needs_user_token, user_login
from app.runner import execute


def endpoint():
    return SimpleNamespace(
        method="GET", url="{{baseUrl}}/api/me",
        request={"auth": {"type": "bearer", "bearer": [
            {"key": "token", "value": "{{userAccessToken}}"}]}, "header": []})


def test_login_extracts_token_without_bearer_prefix():
    def handler(request):
        assert request.url.path == "/api/auth/login"
        assert request.headers.get("authorization") is None
        assert request.method == "POST"
        return httpx.Response(200, json={
            "success": True, "data": {"accessToken": "Bearer token-123"}})
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handler))):
        assert user_login("http://example.test", "user@sample.test", "password") == "token-123"


def test_login_failure_does_not_expose_credentials():
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(401, text="invalid password")))):
        with pytest.raises(LoginError) as error:
            user_login("http://example.test", "user@sample.test", "secret-password")
    assert "secret-password" not in str(error.value)


def test_bearer_header_attached_only_when_token_given():
    captured = []
    def handler(request):
        captured.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"success": True})
    assert needs_user_token(endpoint())
    assert execute(endpoint(), {"baseUrl": "http://example.test"})["status"] == "BLOCKED"
    with patch("app.runner.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handler))):
        result = execute(endpoint(), {"baseUrl": "http://example.test"},
                         user_access_token="token-123")
    assert result["status"] == "PASS"
    assert captured == ["Bearer token-123"]


def test_unknown_bearer_profile_is_blocked():
    other = endpoint()
    other.request["auth"]["bearer"][0]["value"] = "{{adminAccessToken}}"
    assert not needs_user_token(other)
    assert execute(other, {"baseUrl": "http://example.test"},
                   user_access_token="token-123")["status"] == "BLOCKED"
