"""Adaptive AI only selects among already approved pending endpoints."""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.ai_adaptive import validate_decision, choose_next, move_next

A = "a" * 64
B = "b" * 64
C = "c" * 64


def ep(method="GET", name="read"):
    return SimpleNamespace(method=method, name=name)


def test_reorder_is_stable_and_cannot_invent_endpoints():
    pending = [(A, ep()), (B, ep("DELETE", "remove")), (C, ep())]
    assert [key for key, _ in move_next(pending, B)] == [B, A, C]
    assert [key for key, _ in pending] == [A, B, C]
    with pytest.raises(ValueError):
        move_next(pending, "unknown")


@pytest.mark.parametrize("bad", [
    {"action": "continue", "next_id": "999", "reason": "invalid"},
    {"action": "continue", "next_id": "0", "reason": "ok", "url": "/wrong"},
    {"action": "stop", "next_id": "0", "reason": "not empty"},
])
def test_bad_ai_decision_rejected(bad):
    with pytest.raises(ValueError):
        validate_decision(bad, {"0": A})


def test_stop_decision_valid():
    assert validate_decision({"action": "stop", "next_id": "", "reason": "중단"},
                             {"0": A})["action"] == "stop"


def test_network_ai_sees_only_status_and_approved_candidates():
    def handler(request):
        payload = json.loads(request.content)
        content = json.loads(payload["input"])
        assert "password" not in payload["input"]
        assert "secret" not in payload["input"]
        assert payload["store"] is False
        assert payload["max_output_tokens"] <= 350
        assert content["recent"] == [{"status": "FAIL", "http": 404, "method": "GET"}]
        assert {r["id"] for r in content["remaining"]} == {"0", "1"}
        body = {"action": "continue", "next_id": "1", "reason": "독립 조회 확인"}
        return httpx.Response(200, json={
            "status": "completed",
            "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps(body)}]}],
            "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100}})
    real_client = httpx.Client
    with patch("app.ai_adaptive.httpx.Client", side_effect=lambda **kwargs:
               real_client(transport=httpx.MockTransport(handler), **kwargs)):
        decision, usage = choose_next("test-key", "gpt-5-mini",
            [{"status": "FAIL", "http_status": 404, "method": "GET"}],
            [(A, ep()), (B, ep("GET", "other"))])
    assert decision["next_id"] == B
    assert usage["total_tokens"] == 100


def test_network_ai_rejects_nonapproved_id():
    def handler(_):
        return httpx.Response(200, json={"status": "completed", "output": [{
            "type": "message", "content": [{
                "type": "output_text",
                "text": json.dumps({"action": "continue", "next_id": "10",
                                    "reason": "wrong"})}]}]})
    real_client = httpx.Client
    with patch("app.ai_adaptive.httpx.Client", side_effect=lambda **kwargs:
               real_client(transport=httpx.MockTransport(handler), **kwargs)):
        with pytest.raises(ValueError):
            choose_next("key", "gpt-5-mini",
                        [{"status": "FAIL", "http_status": 400, "method": "GET"}],
                        [(A, ep())])
