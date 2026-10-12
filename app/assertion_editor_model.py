"""GUI-friendly rule creation without requiring users to write JSON arrays."""
import json

from .assertions import validate_rules

KINDS = ("status", "exists", "equals", "value_type", "range", "length")


def parse_rule_fields(kind, path="", expected="", minimum="", maximum=""):
    if kind not in KINDS:
        raise ValueError("지원하지 않는 검증 유형입니다.")
    rule = {"type": kind}
    if kind == "status":
        try:
            rule["expected"] = int(expected)
        except (TypeError, ValueError):
            raise ValueError("HTTP 상태 코드는 정수여야 합니다.") from None
    else:
        rule["path"] = path.strip()
        if kind == "equals":
            try:
                rule["expected"] = json.loads(expected)
            except (TypeError, ValueError):
                raise ValueError("예상값은 올바른 JSON 값이어야 합니다. 문자열 예: \"hello\"") from None
        elif kind == "value_type":
            rule["expected"] = expected
        elif kind in ("range", "length"):
            for label, raw in (("min", minimum), ("max", maximum)):
                if raw.strip():
                    try:
                        rule[label] = json.loads(raw)
                    except ValueError:
                        raise ValueError(f"{label} 값은 숫자여야 합니다.") from None
    return validate_rules([rule])[0]


def describe_rule(rule):
    kind = rule["type"]
    path = rule.get("path", "HTTP")
    if kind == "exists":
        return f"{path} 존재"
    if kind == "status":
        return f"HTTP 상태 = {rule['expected']}"
    if kind == "equals":
        return f"{path} = {json.dumps(rule['expected'], ensure_ascii=False)}"
    if kind == "value_type":
        return f"{path} 타입 = {rule['expected']}"
    return f"{path} {kind} ({rule.get('min', '—')} ~ {rule.get('max', '—')})"
