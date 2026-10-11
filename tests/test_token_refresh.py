"""Mock USER/ADMIN refresh endpoints; no external API calls."""
import json
from unittest.mock import patch
import httpx
import pytest

from app.user_auth import login_tokens, refresh_tokens, LoginError


@pytest.mark.parametrize("profile,path", [
    ("USER", "/api/auth/refresh"),
    ("ADMIN", "/api/backoffice/auth/refresh"),
])
def test_refresh_uses_expected_endpoint_and_rotates(profile, path):
    def handle(request):
        assert request.url.path == path
        assert json.loads(request.content) == {"refreshToken": "old-refresh"}
        return httpx.Response(200, json={"success": True, "data": {
            "accessToken": "new-access", "refreshToken": "new-refresh"}})
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(handle))):
        assert refresh_tokens(profile, "https://example.test", "old-refresh") == (
            "new-access", "new-refresh")


def test_refresh_keeps_existing_refresh_if_server_returns_only_access():
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(
                200, json={"success": True, "data": {"accessToken": "new"}})))):
        assert refresh_tokens("USER", "https://example.test", "old") == ("new", "old")


def test_login_returns_access_and_refresh():
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(
                200, json={"success": True, "data": {
                    "accessToken": "Bearer a", "refreshToken": "r"}})))):
        assert login_tokens("USER", "https://example.test", "name", "password") == ("a", "r")


def test_refresh_failure_never_leaks_tokens():
    with patch("app.user_auth.httpx.Client", return_value=httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(
                401, text="sensitive-response")))):
        with pytest.raises(LoginError) as err:
            refresh_tokens("ADMIN", "https://example.test", "secret-refresh")
    assert "secret-refresh" not in str(err.value)
    assert "sensitive-response" not in str(err.value)
