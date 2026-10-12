"""Safe, bounded response assertions. No response bodies or values persisted."""
import json
import math

from .json_paths import find_path, path_parts

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_RULES = 20
VALUE_TYPES = {"string": str, "number": (int, float), "integer": int,
               "boolean": bool, "array": list, "object": dict, "null": type(None)}


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
            continue
        if kind not in ("exists", "equals", "value_type", "range", "length"):
            raise ValueError("지원하지 않는 검증 유형입니다.")
        path = rule.get("path")
        path_parts(path)
        entry = {"type": kind, "path": path}
        if kind == "equals":
            if "expected" not in rule:
                raise ValueError("equals에는 expected 값이 필요합니다.")
            entry["expected"] = rule["expected"]
        if kind == "value_type":
            expected = rule.get("expected")
            if not isinstance(expected, str) or expected not in VALUE_TYPES:
                raise ValueError("지원하지 않는 JSON 타입입니다.")
            entry["expected"] = expected
        if kind in ("range", "length"):
            low, high = rule.get("min"), rule.get("max")
            if low is None and high is None:
                raise ValueError("min 또는 max 중 하나는 필수입니다.")
            for value in (low, high):
                if value is None:
                    continue
                if kind == "length":
                    if type(value) is not int or value < 0:
                        raise ValueError("길이는 0 이상의 정수여야 합니다.")
                elif type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("범위는 유한한 숫자여야 합니다.")
            if low is not None and high is not None and low > high:
                raise ValueError("min은 max 이하여야 합니다.")
            if low is not None:
                entry["min"] = low
            if high is not None:
                entry["max"] = high
        cleaned.append(entry)
    if len(json.dumps(cleaned, ensure_ascii=False)) > 8192:
        raise ValueError("검증 규칙은 8KB를 초과할 수 없습니다.")
    return cleaned


def _matches_type(value, expected):
    if expected == "number":
        return type(value) in (int, float)
    return type(value) is VALUE_TYPES[expected]


def evaluate_response(response, rules):
    """Return indexed failure reason and path, never actual or expected values."""
    rules = validate_rules(rules)
    if not rules:
        return True, ""
    payload = None
    if any(rule["type"] != "status" for rule in rules):
        if len(response.content) > MAX_RESPONSE_BYTES:
            return False, "응답 JSON 검증 실패: 응답 크기 제한 초과"
        try:
            payload = response.json()
        except ValueError:
            return False, "응답 JSON 검증 실패: JSON 형식 아님"
    for i, rule in enumerate(rules, start=1):
        kind = rule["type"]
        if kind == "status":
            passed = response.status_code == rule["expected"]
        else:
            found, node = find_path(payload, rule["path"])
            if kind == "exists":
                passed = found
            elif kind == "equals":
                passed = found and type(node) is type(rule["expected"]) and node == rule["expected"]
            elif kind == "value_type":
                passed = found and _matches_type(node, rule["expected"])
            elif kind == "range":
                passed = found and type(node) in (int, float) and math.isfinite(node) and (
                    "min" not in rule or node >= rule["min"]) and (
                    "max" not in rule or node <= rule["max"])
            else:
                passed = found and type(node) in (str, list, dict) and (
                    "min" not in rule or len(node) >= rule["min"]) and (
                    "max" not in rule or len(node) <= rule["max"])
        if not passed:
            location = f" @ {rule['path']}" if "path" in rule else ""
            return False, f"검증 규칙 {i} 실패 ({kind}{location})"
    return True, f"검증 {len(rules)}개 통과"
