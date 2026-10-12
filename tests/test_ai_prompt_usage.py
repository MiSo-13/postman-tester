"""OpenAI usage metadata and conservative token budgets."""
import json
from types import SimpleNamespace
from unittest.mock import patch
import httpx

from app.ai_planner_client import generate_plan
from app.ai_planner_prompt import planner_instructions
from app.ai_usage import parse_usage, add_usage, empty_usage, usage_summary


KEY = "a" * 64


def test_prompt_constraints():
    prompt = planner_instructions().lower()
    for term in ("untrusted", "dependency", "authorization", "destructive", "korean", "max_steps"):
        assert term in prompt


def test_usage_parser_and_accumulator():
    data = {"usage": {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
           "input_tokens_details": {"cached_tokens": 20},
           "output_tokens_details": {"reasoning_tokens": 4}}}
    usage = parse_usage(data)
    assert usage == {"input_tokens": 120, "output_tokens": 30, "total_tokens": 150,
                     "cached_tokens": 20, "reasoning_tokens": 4}
    assert add_usage(empty_usage(), usage)["total_tokens"] == 150
    assert "150" in usage_summary(usage)
    assert parse_usage({"usage": {"input_tokens": -1}}) is None


def test_compact_catalog_and_token_budget():
    observed = {}
    def handler(request):
        body = json.loads(request.content)
        observed.update(body)
        catalog = json.loads(body["input"])["catalog"]
        assert catalog[0]["id"] == "0"
        assert KEY not in body["input"]
        return httpx.Response(200, json={
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            "output": [{"type": "message", "content": [{"type": "output_text",
                "text": json.dumps({"steps": [{"key": "0", "reason": "간단한 목록 확인"}]})}]}]})
    original = httpx.Client
    ep = SimpleNamespace(method="GET", name="items", url="{{baseUrl}}/items",
                         request={"auth": {"type": "noauth"}})
    with patch("app.ai_planner_client.httpx.Client", side_effect=lambda **kw:
               original(transport=httpx.MockTransport(handler), **kw)):
        plan = generate_plan("example", "gpt-5-mini", [KEY], [ep], max_steps=2)
    assert plan["steps"][0]["key"] == KEY
    assert plan["_usage"]["total_tokens"] == 120
    assert observed["max_output_tokens"] <= 1000
    assert observed["reasoning"]["effort"] == "low"
    assert observed["store"] is False
