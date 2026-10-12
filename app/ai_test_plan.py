"""AI test planning: data-only catalog, strict plan validation, no arbitrary execution."""
import json

from .scenarios import validate_steps

MAX_CATALOG = 100
MAX_STEPS = 30


def build_catalog(keys, endpoints):
    if len(keys) != len(endpoints):
        raise ValueError("Collection 키와 API 목록이 일치하지 않습니다.")
    return [{"key": key, "method": ep.method, "url": ep.url,
             "name": ep.name, "auth": (ep.request.get("auth") or {}).get("type", "noauth")}
            for key, ep in list(zip(keys, endpoints))[:MAX_CATALOG]]


def validate_ai_plan(plan, catalog):
    if not isinstance(plan, dict) or not isinstance(plan.get("steps"), list):
        raise ValueError("AI 계획이 올바른 JSON 객체가 아닙니다.")
    raw_steps = plan["steps"]
    if not 1 <= len(raw_steps) <= MAX_STEPS:
        raise ValueError("AI 계획은 1~30개 단계여야 합니다.")
    keys = {x["key"] for x in catalog}
    steps = []
    for entry in raw_steps:
        if not isinstance(entry, dict) or set(entry) != {"key", "reason"}:
            raise ValueError("단계는 key와 reason만 포함해야 합니다.")
        if entry["key"] not in keys:
            raise ValueError("Collection에 존재하지 않는 API가 계획에 포함되었습니다.")
        if not isinstance(entry["reason"], str) or len(entry["reason"]) > 300:
            raise ValueError("단계 설명이 유효하지 않습니다.")
        steps.append(entry["key"])
    validate_steps(steps, keys)
    return {"steps": raw_steps}


PLAN_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"steps": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"key": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["key", "reason"]}}},
    "required": ["steps"]
}


def parse_response_text(response):
    if response.get("status") != "completed":
        raise ValueError("AI 응답이 완료되지 않았습니다.")
    for part in response.get("output", []):
        if part.get("type") == "message":
            for item in part.get("content", []):
                if item.get("type") == "output_text":
                    return json.loads(item["text"])
    raise ValueError("AI 응답에 테스트 계획이 없습니다.")
