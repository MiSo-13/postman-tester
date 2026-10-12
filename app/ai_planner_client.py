"""Optional OpenAI Responses API adapter, isolated from the test runner."""
import json

import httpx

from .ai_test_plan import PLAN_SCHEMA, build_catalog, parse_response_text, validate_ai_plan
from .ai_planner_prompt import planner_instructions
from .ai_usage import parse_usage


class AIPlanningError(ValueError):
    pass


def generate_plan(api_key, model, endpoint_keys, endpoints, *, max_steps=15,
                  allow_writes=False, timeout=60):
    if not isinstance(api_key, str) or not api_key.strip():
        raise AIPlanningError("OpenAI API Key를 입력하세요.")
    if not isinstance(model, str) or not model.strip() or len(model) > 80:
        raise AIPlanningError("모델 이름을 확인하세요.")
    if type(max_steps) is not int or not 1 <= max_steps <= 30:
        raise AIPlanningError("최대 단계 수는 1~30입니다.")
    catalog = build_catalog(endpoint_keys, endpoints)
    if not allow_writes:
        catalog = [entry for entry in catalog if entry["method"].upper() in ("GET", "HEAD", "OPTIONS")]
    if not catalog:
        raise AIPlanningError("AI 계획을 생성할 API가 없습니다.")
    instruction = planner_instructions()
    # Compact per-request aliases avoid sending 64-character SHA keys repeatedly.
    aliases = {str(i): entry["key"] for i, entry in enumerate(catalog)}
    compact_catalog = [
        {"id": str(i), "m": entry["method"], "u": entry["url"][:180],
         "n": entry["name"][:90], "a": entry["auth"]}
        for i, entry in enumerate(catalog)
    ]
    request_body = {
        "model": model,
        "instructions": instruction,
        "input": json.dumps({"max_steps": max_steps, "catalog": compact_catalog}, ensure_ascii=False, separators=(",", ":")),
        "text": {"format": {"type": "json_schema", "name": "api_test_plan",
                            "strict": True, "schema": PLAN_SCHEMA}},
        "store": False,
        "max_output_tokens": min(3800, 600 + max_steps * 110)
    }
    if model.startswith(("gpt-5", "o3", "o4")):
        request_body["reasoning"] = {"effort": "low"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": "Bearer " + api_key.strip(),
                         "Content-Type": "application/json"},
                json=request_body)
        if response.status_code != 200:
            raise AIPlanningError(f"AI 계획 생성 실패: OpenAI HTTP {response.status_code}")
        payload = response.json()
        plan = parse_response_text(payload)
        if isinstance(plan, dict) and isinstance(plan.get("steps"), list):
            for step in plan["steps"]:
                if isinstance(step, dict) and step.get("key") in aliases:
                    step["key"] = aliases[step["key"]]
        checked = validate_ai_plan(plan, catalog)
        if len(checked["steps"]) > max_steps:
            raise AIPlanningError("요청한 최대 단계 수를 초과했습니다.")
        checked["_usage"] = parse_usage(payload)
        return checked
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
        raise AIPlanningError(f"AI 계획을 가져올 수 없습니다: {type(exc).__name__}") from None
