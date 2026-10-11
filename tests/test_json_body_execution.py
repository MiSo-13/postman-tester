"""Tests for JSON Body execution; no live API calls."""
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.runner import execute


def endpoint(method="POST", body=None, auth=None):
    request = {"header": [], "body": body if body is not None else {
        "mode": "raw", "raw": '{"name":"default"}', "options": {"raw": {"language": "json"}}
    }}
    if auth is not None:
        request["auth"] = auth
    return SimpleNamespace(method=method, url="{{baseUrl}}/api/test", request=request)


def test_saved_json_is_sent_without_comments():
    requests = []

    def handler(request):
        requests.append(request)
        return __import__("httpx").Response(200, json={"success": True})

    import httpx
    with patch("app.runner.httpx.Client", return_value=httpx.Client(transport=httpx.MockTransport(handler))):
        result = execute(endpoint(), {"baseUrl": "http://example.test"}, allow_writes=True,
                         raw_body_override='{"url":"https://example.test/a//b", // comment\n "value":2}')
    assert result["status"] == "PASS"
    assert len(requests) == 1
    assert json.loads(requests[0].content) == {"url": "https://example.test/a//b", "value": 2}
    assert requests[0].headers["content-type"] == "application/json"


def test_default_body_and_variable_substitution():
    captured = []
    import httpx
    with patch("app.runner.httpx.Client", return_value=httpx.Client(
        transport=httpx.MockTransport(lambda request: (
            captured.append(request) or httpx.Response(201))))):
        result = execute(endpoint(body={"mode": "raw", "raw": '{"id":"{{itemId}}"}'}),
                         {"baseUrl": "http://example.test", "itemId": "42"}, allow_writes=True)
    assert result["status"] == "PASS"
    assert json.loads(captured[0].content) == {"id": "42"}


def test_write_protection_and_invalid_json_make_no_network_call():
    with patch("app.runner.httpx.Client") as client:
        assert execute(endpoint(), {"baseUrl": "http://example.test"})["status"] == "SKIPPED"
        result = execute(endpoint(), {"baseUrl": "http://example.test"}, allow_writes=True,
                         raw_body_override='{"broken":}')
        assert result["status"] == "BLOCKED"
        client.assert_not_called()


def test_auth_and_multipart_blocked():
    with patch("app.runner.httpx.Client") as client:
        e = endpoint(auth={"type": "bearer"})
        assert execute(e, {"baseUrl": "http://example.test"}, allow_writes=True)["status"] == "BLOCKED"
        multipart = endpoint(body={"mode": "formdata", "formdata": []})
        assert execute(multipart, {"baseUrl": "http://example.test"}, allow_writes=True)["status"] == "BLOCKED"
        client.assert_not_called()
