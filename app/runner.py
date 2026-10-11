"""Conservative HTTP executor with JSONC request-body support."""
import json
import re
import time

import httpx

from .request_overrides import strip_json_comments

VAR = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")


def substitute(value: str, variables: dict) -> str:
    def replace(match):
        name = match.group(1)
        if name not in variables or variables[name] in (None, ""):
            raise ValueError(f"설정되지 않은 변수: {name}")
        return str(variables[name])
    return VAR.sub(replace, value)


def _blocked(reason: str) -> dict:
    return {"status": "BLOCKED", "http_status": None, "elapsed_ms": None, "detail": reason}


def execute(endpoint, variables: dict, timeout: float = 20,
            verify_ssl: bool = True, allow_writes: bool = False,
            raw_body_override: str | None = None) -> dict:
    """Only send supported request shapes; all checks precede the HTTP call."""
    method = endpoint.method.upper()
    if method not in ("GET", "HEAD", "OPTIONS") and not allow_writes:
        return {"status": "SKIPPED", "http_status": None, "elapsed_ms": None,
                "detail": "쓰기 요청은 setting.json에서 명시적으로 허용해야 합니다."}
    request = endpoint.request
    auth = request.get("auth") or {}
    # Inherited Collection/folder auth is not yet modeled: fail closed.
    if isinstance(auth, dict) and auth.get("type") not in (None, "noauth"):
        return _blocked("인증 요청은 아직 지원하지 않습니다.")
    headers_source = request.get("header", [])
    if not isinstance(headers_source, list):
        return _blocked("지원하지 않는 Header 형식입니다.")
    body = request.get("body") or {}
    if raw_body_override is not None and body.get("mode") != "raw":
        return _blocked("Raw JSON이 아닌 API에는 JSON 수정값을 사용할 수 없습니다.")
    if body and body.get("mode") != "raw":
        return _blocked("Multipart/Form-data 등은 아직 지원하지 않습니다.")
    if body and body.get("options", {}).get("raw", {}).get("language", "json") != "json":
        return _blocked("JSON 이외의 Raw Body는 아직 지원하지 않습니다.")

    try:
        url = substitute(endpoint.url, variables)
        headers = {
            h["key"]: substitute(str(h.get("value", "")), variables)
            for h in headers_source
            if h.get("key") and not h.get("disabled", False)
        }
        if any(k.lower() == "authorization" for k in headers):
            return _blocked("인증 Header 자동 처리 기능은 아직 지원하지 않습니다.")
        payload = None
        if body:
            source = raw_body_override if raw_body_override is not None else body.get("raw", "")
            # Do not send invalid or unresolved JSON; strip comments before network I/O.
            clean = substitute(strip_json_comments(source), variables)
            parsed = json.loads(clean)
            if not isinstance(parsed, (dict, list)):
                raise ValueError("JSON Body는 객체 또는 배열이어야 합니다.")
            payload = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/json"
        started = time.monotonic()
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.request(method, url, headers=headers, content=payload)
        elapsed = round((time.monotonic() - started) * 1000, 2)
        return {
            "status": "PASS" if 200 <= response.status_code < 300 else "FAIL",
            "http_status": response.status_code, "elapsed_ms": elapsed,
            # Do not store raw responses in unmasked logs/reports.
            "detail": "" if response.status_code < 400 else f"HTTP {response.status_code}",
        }
    except (ValueError, json.JSONDecodeError) as exc:
        return _blocked(f"요청 구성이 올바르지 않습니다: {exc}")
    except httpx.HTTPError as exc:
        return {"status": "ERROR", "http_status": None, "elapsed_ms": None,
                "detail": f"HTTP 연결/전송 오류: {type(exc).__name__}"}
