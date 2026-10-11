"""Initial safe HTTP runner: sequential, read-only by default."""
import re
import time
import httpx

VAR = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")


def substitute(value: str, variables: dict) -> str:
    def replace(match):
        name = match.group(1)
        if name not in variables or variables[name] in (None, ""):
            raise ValueError(f"설정되지 않은 변수: {name}")
        return str(variables[name])
    return VAR.sub(replace, value)


def execute(endpoint, variables: dict, timeout: float = 20,
            verify_ssl: bool = True, allow_writes: bool = False) -> dict:
    method = endpoint.method.upper()
    if method not in ("GET", "HEAD", "OPTIONS") and not allow_writes:
        return {"status": "SKIPPED", "http_status": None, "elapsed_ms": None,
                "detail": "쓰기 요청은 설정에서 명시적으로 허용해야 합니다."}
    try:
        url = substitute(endpoint.url, variables)
        headers = {h["key"]: substitute(str(h.get("value", "")), variables)
                   for h in endpoint.request.get("header", [])
                   if h.get("key") and not h.get("disabled", False)}
        # Initial MVP: do not claim to support request bodies / multipart / auth yet.
        if endpoint.request.get("body") or endpoint.request.get("auth", {}).get("type") not in (None, "noauth"):
            return {"status": "BLOCKED", "http_status": None, "elapsed_ms": None,
                    "detail": "Body/인증 요청은 다음 단계 실행 엔진에서 지원합니다."}
        started = time.monotonic()
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.request(method, url, headers=headers)
        elapsed = round((time.monotonic() - started) * 1000, 2)
        return {"status": "PASS" if 200 <= response.status_code < 300 else "FAIL",
                "http_status": response.status_code, "elapsed_ms": elapsed,
                "detail": response.text[:2000] if response.status_code >= 400 else ""}
    except (ValueError, httpx.HTTPError) as exc:
        return {"status": "ERROR", "http_status": None, "elapsed_ms": None, "detail": str(exc)}
