"""Safely extract bounded scalar values from successful JSON responses."""
import json
import re

NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
FORBIDDEN = {"baseUrl", "userAccessToken", "adminAccessToken"}
MAX_BYTES = 1024 * 1024


def validate_extractions(rules):
    if not isinstance(rules, list) or len(rules) > 20:
        raise ValueError("추출 규칙은 최대 20개 배열이어야 합니다.")
    cleaned, seen = [], set()
    for item in rules:
        if not isinstance(item, dict):
            raise ValueError("추출 규칙은 JSON 객체여야 합니다.")
        name, path = item.get("name"), item.get("path")
        if (not isinstance(name, str) or not NAME.fullmatch(name)
                or name in FORBIDDEN or name.lower().endswith("token")
                or name in seen):
            raise ValueError("중복 또는 금지된 변수 이름입니다.")
        if (not isinstance(path, str) or not path or len(path) > 256
                or any(not part or part.startswith("_") or "[" in part or "]" in part
                       for part in path.split("."))):
            raise ValueError("JSON 경로는 점(.)으로 구분한 객체 키만 허용합니다.")
        seen.add(name)
        cleaned.append({"name": name, "path": path})
    if len(json.dumps(cleaned, ensure_ascii=False)) > 8192:
        raise ValueError("추출 규칙 크기가 너무 큽니다.")
    return cleaned


def extract_values(response, rules):
    """Return only values to memory; never log response body or extracted values."""
    rules = validate_extractions(rules)
    if not rules:
        return {}
    if response.status_code < 200 or response.status_code >= 300:
        raise ValueError("성공하지 않은 HTTP 응답에서 변수를 추출할 수 없습니다.")
    if len(response.content) > MAX_BYTES:
        raise ValueError("변수 추출 응답 크기가 제한을 초과했습니다.")
    try:
        document = response.json()
    except ValueError:
        raise ValueError("변수 추출 응답이 JSON이 아닙니다.") from None
    extracted = {}
    for rule in rules:
        node = document
        for part in rule["path"].split("."):
            if not isinstance(node, dict) or part not in node:
                raise ValueError("변수 추출 경로가 응답에 없습니다.")
            node = node[part]
        if isinstance(node, bool) or not isinstance(node, (str, int, float)):
            raise ValueError("변수는 문자열 또는 숫자 값만 추출할 수 있습니다.")
        value = str(node)
        if not value or len(value) > 2048 or "\r" in value or "\n" in value:
            raise ValueError("추출된 변수 값이 유효하지 않습니다.")
        extracted[rule["name"]] = value
    return extracted
