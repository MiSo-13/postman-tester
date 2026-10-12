"""Memory-only defensive JSON preview: never persist arbitrary response content."""
import json
import re

MAX_PREVIEW_BYTES = 32 * 1024
SENSITIVE = re.compile(r"(token|secret|pass(word)?|authorization|cookie|api.?key|email|phone|address|session|credential|ssn|birth|name)", re.I)


def safe_json_preview(response):
    raw = response.content
    if len(raw) > MAX_PREVIEW_BYTES:
        return "응답 본문이 32KB를 초과하여 미리보기를 표시하지 않습니다."
    try:
        payload = response.json()
    except (ValueError, UnicodeError):
        return "JSON이 아닌 응답은 보안을 위해 미리보기를 표시하지 않습니다."

    def redact(value, depth=0):
        if depth > 16:
            return "[DEPTH LIMIT]"
        if isinstance(value, dict):
            return {str(key): "[REDACTED]" if SENSITIVE.search(str(key))
                    else redact(item, depth + 1) for key, item in list(value.items())[:200]}
        if isinstance(value, list):
            return [redact(item, depth + 1) for item in value[:200]]
        if isinstance(value, str):
            # Field names cannot catch anonymous secrets. Mask all string values by default.
            return "[STRING REDACTED]"
        return value if value is None or isinstance(value, (bool, int, float)) else "[REDACTED]"

    return json.dumps(redact(payload), ensure_ascii=False, indent=2)
