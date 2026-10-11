"""Multipart execution uses local files and blocks unsafe paths before HTTP."""
from types import SimpleNamespace
from unittest.mock import patch
import httpx

from app.runner import execute


def endpoint(entries, method="POST"):
    return SimpleNamespace(method=method, url="https://example.test/upload",
        request={"header": [], "body": {"mode": "formdata", "formdata": entries}})


def test_upload_file_and_text_fields(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "example.txt").write_bytes(b"sample-content")
    captured = []
    def handler(request):
        captured.append(request)
        return httpx.Response(200)
    original_client = httpx.Client
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: original_client(
            transport=httpx.MockTransport(handler), **kwargs)):
        result = execute(endpoint([
            {"key": "description", "value": "{{name}}", "type": "text"},
            {"key": "attachment", "type": "file", "src": "example.txt"},
            {"key": "unused", "type": "file", "src": "missing.txt", "disabled": True},
        ]), {"name": "example"}, allow_writes=True, file_root=folder)
    assert result["status"] == "PASS"
    assert len(captured) == 1
    request = captured[0]
    assert "multipart/form-data" in request.headers["content-type"]
    assert b"sample-content" in request.content
    assert b"example" in request.content


def test_missing_file_is_blocked_before_request(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    with patch("app.runner.httpx.Client") as client:
        result = execute(endpoint([{"key": "upload", "type": "file", "src": "missing.txt"}]),
                         {}, allow_writes=True, file_root=root)
    assert result["status"] == "BLOCKED"
    client.assert_not_called()


def test_parent_traversal_blocked_before_request(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("sensitive")
    with patch("app.runner.httpx.Client") as client:
        result = execute(endpoint([{"key": "upload", "type": "file", "src": "../secret.txt"}]),
                         {}, allow_writes=True, file_root=root)
    assert result["status"] == "BLOCKED"
    client.assert_not_called()


def test_symlink_outside_root_blocked(tmp_path):
    root = tmp_path / "uploads"
    root.mkdir()
    external = tmp_path / "external.txt"
    external.write_text("secret")
    (root / "external.txt").symlink_to(external)
    with patch("app.runner.httpx.Client") as client:
        result = execute(endpoint([{"key": "upload", "type": "file", "src": "external.txt"}]),
                         {}, allow_writes=True, file_root=root)
    assert result["status"] == "BLOCKED"
    client.assert_not_called()


def test_writes_disabled_by_default(tmp_path):
    with patch("app.runner.httpx.Client") as client:
        result = execute(endpoint([{"key": "field", "value": "hello", "type": "text"}]), {},
                         file_root=tmp_path)
    assert result["status"] == "SKIPPED"
    client.assert_not_called()
