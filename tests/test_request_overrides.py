"""Regression tests for JSONC editing and project-scoped persistence."""
import json

import pytest

from app.postman import Endpoint
from app.request_overrides import endpoint_key, strip_json_comments, validate_raw_json
from app.storage import Storage


def endpoint(name="로그인"):
    return Endpoint("인증", name, "POST", "{{baseUrl}}/api/auth/login", {}, [], [])


def test_comments_keep_string_literals():
    source = '{"url":"https://example.com/a//b", // 설명\n "note":"/* literal */", /* block */ "ok":true}'
    parsed = json.loads(strip_json_comments(source))
    assert parsed == {"url": "https://example.com/a//b", "note": "/* literal */", "ok": True}
    validate_raw_json(source)


@pytest.mark.parametrize("text", ['{"a": }', '{"a":1', '/* unclosed', "123"])
def test_invalid_json_rejected(text):
    with pytest.raises(ValueError):
        validate_raw_json(text)


def test_project_scoping_restart_and_restore(tmp_path):
    data = tmp_path / "data"
    storage = Storage(data)
    first = storage.create_project("A")
    second = storage.create_project("B")
    key = endpoint_key(endpoint())
    raw = '{\n "url": "https://example.com", // comment\n "value": 3\n}'
    storage.save_request_override(first, key, raw)

    reopened = Storage(data)
    assert reopened.get_request_override(first, key) == raw
    assert reopened.get_request_override(second, key) is None
    assert reopened.get_request_override(first, endpoint_key(endpoint("다른 API"))) is None
    reopened.remove_request_override(first, key)
    assert reopened.get_request_override(first, key) is None
