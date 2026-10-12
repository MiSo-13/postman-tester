"""Turn already-redacted response previews into safe assertion candidates."""
import json
import re

from .assertions import validate_rules
from .json_paths import path_parts

KEY = re.compile(r"^[A-Za-z0-9-]+$")
MASKS = frozenset(("[REDACTED]", "[STRING REDACTED]", "[DEPTH LIMIT]"))


def candidates_from_preview(preview):
    """Never expose unredacted response data; rejects unavailable previews."""
    try:
        data = json.loads(preview)
    except (ValueError, TypeError):
        return []
    found = []

    def visit(node, path="", depth=0):
        if depth > 16 or len(found) >= 200:
            return
        if path:
            try:
                path_parts(path)
            except ValueError:
                pass
            else:
                found.append((path, node))
        if isinstance(node, dict):
            for key, value in list(node.items())[:100]:
                if KEY.fullmatch(key) and not key.startswith("_"):
                    visit(value, f"{path}.{key}" if path else key, depth + 1)
        elif isinstance(node, list):
            for index, value in enumerate(node[:30]):
                visit(value, f"{path}[{index}]", depth + 1)

    visit(data)
    return found


def rule_from_candidate(path, value, kind):
    path_parts(path)
    if kind == "exists":
        rule = {"type": "exists", "path": path}
    elif kind == "value_type":
        if isinstance(value, str) and value in MASKS:
            raise ValueError("마스킹된 값은 타입을 확정할 수 없습니다.")
        if value is None:
            name = "null"
        elif type(value) is bool:
            name = "boolean"
        elif type(value) is int:
            name = "integer"
        elif type(value) is float:
            name = "number"
        elif isinstance(value, list):
            name = "array"
        elif isinstance(value, dict):
            name = "object"
        else:
            name = "string"
        rule = {"type": "value_type", "path": path, "expected": name}
    elif kind == "equals":
        if type(value) not in (int, float, bool) and value is not None:
            raise ValueError("문자열·객체 값은 안전한 자동 일치 검증을 지원하지 않습니다.")
        rule = {"type": "equals", "path": path, "expected": value}
    else:
        raise ValueError("지원하지 않는 자동 검증 종류입니다.")
    return validate_rules([rule])[0]
