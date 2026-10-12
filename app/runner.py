"""Conservative HTTP executor with JSONC request-body support."""
import json
from contextlib import ExitStack
from pathlib import Path
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
            raw_body_override: str | None = None,
            user_access_token: str | None = None,
            admin_access_token: str | None = None,
            file_root: Path | None = None,
            assertions: list | None = None,
            extraction_rules: list | None = None,
            captured_variables: dict | None = None,
            client: httpx.Client | None = None,
            preview_callback=None) -> dict:
    """Only send supported request shapes; all checks precede the HTTP call."""
    from .assertions import validate_rules
    try:
        assertions = validate_rules(assertions or [])
    except ValueError:
        return _blocked("응답 검증 규칙이 올바르지 않습니다.")
    from .extractions import validate_extractions
    try:
        extraction_rules = validate_extractions(extraction_rules or [])
    except ValueError:
        return _blocked("변수 추출 규칙이 올바르지 않습니다.")
    method = endpoint.method.upper()
    if method not in ("GET", "HEAD", "OPTIONS") and not allow_writes:
        return {"status": "SKIPPED", "http_status": None, "elapsed_ms": None,
                "detail": "쓰기 요청은 setting.json에서 명시적으로 허용해야 합니다."}
    request = endpoint.request
    auth = request.get("auth") or {}
    # Inherited Collection/folder auth is not yet modeled: fail closed.
    if isinstance(auth, dict) and auth.get("type") not in (None, "noauth", "bearer"):
        return _blocked("지원하지 않는 인증 유형입니다.")
    if isinstance(auth, dict) and auth.get("type") == "bearer":
        from .user_auth import needs_user_token, needs_admin_token
        if needs_user_token(endpoint):
            if not user_access_token:
                return _blocked("USER 로그인 토큰이 없습니다.")
        elif needs_admin_token(endpoint):
            if not admin_access_token:
                return _blocked("ADMIN 로그인 토큰이 없습니다.")
        else:
            return _blocked("지원하지 않는 Bearer 인증 프로필입니다.")
    headers_source = request.get("header", [])
    if not isinstance(headers_source, list):
        return _blocked("지원하지 않는 Header 형식입니다.")
    body = request.get("body") or {}
    if raw_body_override is not None and body.get("mode") != "raw":
        return _blocked("Raw JSON이 아닌 API에는 JSON 수정값을 사용할 수 없습니다.")
    if body and body.get("mode") not in ("raw", "formdata"):
        return _blocked("지원하지 않는 Body 형식입니다.")
    if body and body.get("mode") == "raw" and body.get("options", {}).get("raw", {}).get("language", "json") != "json":
        return _blocked("JSON 이외의 Raw Body는 아직 지원하지 않습니다.")

    try:
        url = substitute(endpoint.url, variables)
        headers = {
            h["key"]: substitute(str(h.get("value", "")), variables)
            for h in headers_source
            if h.get("key") and not h.get("disabled", False)
        }
        if any(k.lower() == "authorization" for k in headers):
            return _blocked("직접 지정한 Authorization Header는 아직 지원하지 않습니다.")
        if isinstance(auth, dict) and auth.get("type") == "bearer":
            from .user_auth import needs_user_token
            token = user_access_token if needs_user_token(endpoint) else admin_access_token
            headers["Authorization"] = f"Bearer {token}"
        payload = None
        if body and body.get("mode") == "raw":
            source = raw_body_override if raw_body_override is not None else body.get("raw", "")
            # Do not send invalid or unresolved JSON; strip comments before network I/O.
            clean = substitute(strip_json_comments(source), variables)
            parsed = json.loads(clean)
            if not isinstance(parsed, (dict, list)):
                raise ValueError("JSON Body는 객체 또는 배열이어야 합니다.")
            payload = json.dumps(parsed, ensure_ascii=False).encode("utf-8")
            if not any(k.lower() == "content-type" for k in headers):
                headers["Content-Type"] = "application/json"
        fields, uploads = [], []
        if body and body.get("mode") == "formdata":
            from .uploads import prepare_formdata
            fields, uploads = prepare_formdata(body, variables, file_root)
            if any(k.lower() == "content-type" for k in headers):
                return _blocked("Multipart Content-Type은 HTTP 라이브러리가 설정해야 합니다.")
        started = time.monotonic()
        with ExitStack() as stack:
            multipart = None
            if body and body.get("mode") == "formdata":
                multipart = [(key, (None, value)) for key, value in fields]
                for key, path, media_type in uploads:
                    handle = stack.enter_context(open(path, "rb"))
                    multipart.append((key, (path.name, handle, media_type)))
            with ExitStack() as transport_stack:
                active_client = client
                if active_client is None:
                    active_client = transport_stack.enter_context(httpx.Client(
                        timeout=timeout, verify=verify_ssl, follow_redirects=False))
                if multipart is not None:
                    response = active_client.request(method, url, headers=headers, files=multipart)
                else:
                    response = active_client.request(method, url, headers=headers, content=payload)
        if preview_callback is not None:
            from .response_preview import safe_json_preview
            preview_callback(safe_json_preview(response))
        elapsed = round((time.monotonic() - started) * 1000, 2)
        from .assertions import evaluate_response
        passed, message = evaluate_response(response, assertions)
        http_ok = 200 <= response.status_code < 300
        if passed and http_ok and extraction_rules:
            from .extractions import extract_values
            try:
                values = extract_values(response, extraction_rules)
            except ValueError:
                return {"status": "FAIL", "http_status": response.status_code,
                        "elapsed_ms": elapsed, "detail": "응답 변수 추출 실패"}
            if captured_variables is not None:
                captured_variables.update(values)
        return {
            "status": "PASS" if passed and (http_ok or any(
                rule["type"] == "status" for rule in assertions)) else "FAIL",
            "http_status": response.status_code, "elapsed_ms": elapsed,
            # Do not log response bodies or expected/actual assertion values.
            "detail": message if assertions else (
                "" if response.status_code < 400 else f"HTTP {response.status_code}"),
        }
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return _blocked(f"요청 구성이 올바르지 않습니다: {exc}")
    except httpx.HTTPError as exc:
        return {"status": "ERROR", "http_status": None, "elapsed_ms": None,
                "detail": f"HTTP 연결/전송 오류: {type(exc).__name__}"}
