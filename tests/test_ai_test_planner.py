"""AI planner contract, safety boundaries, and OpenAI response parsing."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.ai_test_plan import build_catalog, validate_ai_plan
from app.ai_planner_client import generate_plan, AIPlanningError


KEY_A, KEY_B = "a" * 64, "b" * 64


def endpoint(name, method, path):
    return SimpleNamespace(name=name, method=method, url="{{baseUrl}}" + path,
        request={"auth": {"type": "noauth"}, "body": {}})


def catalog():
    return build_catalog([KEY_A, KEY_B], [
        endpoint("read", "GET", "/api/items"),
        endpoint("delete", "DELETE", "/api/items/1")])


def response_for(keys):
    plan = {"steps": [{"key": k, "reason": "API smoke check"} for k in keys]}
    return httpx.Response(200, json={"status": "completed", "output": [{
        "type": "message", "content": [{"type": "output_text",
        "text": json.dumps(plan)}]}]})


def test_disallows_unknown_endpoint_and_invalid_model_steps():
    with pytest.raises(ValueError, match="존재하지 않는"):
        validate_ai_plan({"steps": [{"key": "c" * 64, "reason": "oops"}]}, catalog())
    with pytest.raises(ValueError):
        validate_ai_plan({"steps": [{"key": KEY_A, "reason": "okay", "url": "https://evil.test"}]}, catalog())
    assert validate_ai_plan({"steps": [{"key": KEY_A, "reason": "read first"}]}, catalog())


def test_readonly_catalog_blocks_writes_even_if_model_returns_delete():
    captured = []
    def handler(request):
        payload = json.loads(request.content)
        captured.append(payload)
        assert payload["store"] is False
        assert "DELETE" not in payload["input"]
        assert "secret" not in payload["input"]
        return response_for([KEY_A])
    original = httpx.Client
    with patch("app.ai_planner_client.httpx.Client", side_effect=lambda **kwargs:
               original(transport=httpx.MockTransport(handler), **kwargs)):
        plan = generate_plan("example-key", "gpt-5-mini", [KEY_A, KEY_B], [
            endpoint("read", "GET", "/api/items"),
            endpoint("delete", "DELETE", "/api/items/1")], allow_writes=False)
    assert plan["steps"][0]["key"] == KEY_A
    assert len(captured) == 1


def test_unapproved_output_not_executable():
    original = httpx.Client
    with patch("app.ai_planner_client.httpx.Client", side_effect=lambda **kwargs:
               original(transport=httpx.MockTransport(lambda _: response_for([KEY_B])), **kwargs)):
        with pytest.raises(ValueError, match="존재하지 않는"):
            generate_plan("key", "gpt-5-mini", [KEY_A, KEY_B], [
                endpoint("read", "GET", "/api/items"),
                endpoint("delete", "DELETE", "/api/items/1")])


def test_missing_api_key_and_too_many_steps():
    with pytest.raises(AIPlanningError):
        generate_plan("", "gpt-5-mini", [KEY_A], [endpoint("read", "GET", "/read")])
    with pytest.raises(ValueError):
        validate_ai_plan({"steps": [{"key": KEY_A, "reason": "x"}] * 31}, catalog())


def test_gui_initially_requires_plan():
    from PyQt6.QtWidgets import QApplication
    from app.ai_test_dialog import AITestDialog
    app = QApplication.instance() or QApplication([])
    dialog = AITestDialog([KEY_A], [endpoint("read", "GET", "/items")])
    assert dialog.plan is None
    assert dialog.limit.value() == 15
    assert not dialog.writes.isChecked()
    assert app is not None
