"""Request raw JSON override validation; preserve original commented source."""
import hashlib
import json


def endpoint_key(endpoint, occurrence: int = 0) -> str:
    identity = [endpoint.folder, endpoint.name, endpoint.method, endpoint.url, occurrence]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode("utf-8")).hexdigest()


def strip_json_comments(source: str) -> str:
    """Remove JSONC comments without changing string literals or line numbers."""
    result = []
    i = 0
    in_string = False
    escaped = False
    while i < len(source):
        ch = source[i]
        following = source[i + 1] if i + 1 < len(source) else ""
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
        elif ch == "/" and following == "/":
            result.extend([" ", " "])
            i += 2
            while i < len(source) and source[i] not in "\r\n":
                result.append(" ")
                i += 1
        elif ch == "/" and following == "*":
            result.extend([" ", " "])
            i += 2
            end_found = False
            while i < len(source):
                if source[i:i + 2] == "*/":
                    result.extend([" ", " "])
                    i += 2
                    end_found = True
                    break
                result.append(source[i] if source[i] in "\r\n" else " ")
                i += 1
            if not end_found:
                raise ValueError("닫히지 않은 JSON 블록 주석입니다.")
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def validate_raw_json(source: str) -> None:
    parsed = json.loads(strip_json_comments(source))
    if not isinstance(parsed, (dict, list)):
        raise ValueError("요청 JSON 최상위 항목은 객체 또는 배열이어야 합니다.")
