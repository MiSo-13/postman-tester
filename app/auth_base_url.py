"""Validate a per-project HTTP API base URL before login testing."""
from urllib.parse import urlsplit


def validate_base_url(value):
    if not isinstance(value, str):
        raise ValueError("Base URL을 입력하세요.")
    url = value.strip()
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or any(c.isspace() for c in url)):
        raise ValueError("Base URL은 http(s)://호스트[:포트] 형식이어야 합니다. 경로는 로그인 API에 설정하세요.")
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("Base URL 포트가 올바르지 않습니다.") from None
    return url.rstrip("/")
