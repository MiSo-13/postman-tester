"""Explicit, bounded response assertions without persisting response bodies."""
import json

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RULES = 20


def validate_rules(rules):
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValueError("검증 규칙은 최대 20개 배열이어야 합니다.")
    cleaned = []
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("검증 규칙 형식이 올바르지 않습니다.")
        kind = rule.get("type")
        if kind == "status":
            expected = rule.get("expected")
            if type(expected) is not int or not 100 <= expected <= 599:
                raise ValueError("상태 코드는 100~599 정수여야 합니다.")
            cleaned.append({"type": kind, "expected": expected})
        elif kind in ("exists", "equals"):
            path = rule.get("path")
            if not isinstance(path, str) or not path or len(path) > 256:
                raise ValueError("JSON 경로를 입력하세요.")
            parts = path.split(".")
            if any(not p or p.startswith("_") or "[" in p or "]" in p for p in parts):
                raise ValueError("점(.)으로 구분된 JSON 객체 경로만 허용합니다.")
            result = {"type": kind, "path": path}
            if kind == "equals":
                if "expected" not in rule:
                    raise ValueError("equals에는 expected 값이 필요합니다.")
                result["expected"] = rule["expected"]
            cleaned.append(result)
        else:
            raise ValueError("지원하지 않는 검증 유형입니다.")
    if len(json.dumps(cleaned, ensure_ascii=False)) > 8192:
        raise ValueError("검증 규칙은 8KB를 초과할 수 없습니다.")
    return cleaned


def evaluate_response(response, rules):
    """Only return rule metadata, never expected/actual values or raw response."""
    rules = validate_rules(rules)
    if not rules:
        return True, ""
    json_rules = [r for r in rules if r["type"] != "status"]
    payload = None
    if json_rules:
        if len(response.content) > MAX_RESPONSE_BYTES:
            return False, "응답 JSON 검증 실패: 응답 크기 제한 초과"
        try:
            payload = response.json()
        except ValueError:
            return False, "응답 JSON 검증 실패: JSON 형식 아님"
    for i, rule in enumerate(rules, start=1):
        if rule["type"] == "status":
            passed = response.status_code == rule["expected"]
        else:
            found = True
            node = payload
            for name in rule["path"].split("."):
                if not isinstance(node, dict) or name not in node:
                    found = False
                    break
                node = node[name]
            passed = found if rule["type"] == "exists" else (found and type(node) is type(rule["expected"]) and node == rule["expected"])
        if not passed:
            return False, f"검증 규칙 {i} 실패 ({rule['type']})"
    return True, f"검증 {len(rules)}개 통과"
