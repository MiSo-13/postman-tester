"""Ephemeral USER/ADMIN login. Credentials and tokens are not written to disk."""
import json
import re

import httpx



DEFAULT_LOGIN_CONFIGS = {
    "USER": {"endpoint": "/api/auth/login",
             "identifier_key": "userEmail", "password_key": "userPassword"},
    "ADMIN": {"endpoint": "/api/backoffice/auth/login",
              "identifier_key": "adminId", "password_key": "adminPw"},
}


def validate_login_config(config: dict) -> dict:
    """Allow only relative API paths and ordinary JSON property names."""
    if not isinstance(config, dict):
        raise ValueError("로그인 설정 형식이 올바르지 않습니다.")
    endpoint = config.get("endpoint", "")
    if (not isinstance(endpoint, str) or not endpoint.startswith("/")
            or endpoint.startswith("//") or "?" in endpoint or "#" in endpoint
            or "\\r" in endpoint or "\\n" in endpoint
            or "://" in endpoint or "\\\\" in endpoint):
        raise ValueError("로그인 Endpoint는 /로 시작하는 상대 경로여야 합니다.")
    for key in ("identifier_key", "password_key"):
        value = config.get(key, "")
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError(f"{key}는 단순 JSON 필드 이름이어야 합니다.")
    return {key: config[key] for key in ("endpoint", "identifier_key", "password_key")}


class LoginError(Exception):
    pass


def _login(base_url: str, identifier: str, password: str, *, endpoint: str,
           identifier_key: str, password_key: str,
           timeout: float = 20, verify_ssl: bool = True) -> str:
    if not base_url.startswith(("http://", "https://")):
        raise LoginError("baseUrl은 http 또는 https 주소여야 합니다.")
    if not identifier or not password:
        raise LoginError("이메일과 비밀번호를 입력하세요.")
    url = base_url.rstrip("/") + endpoint
    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.post(url, json={identifier_key: identifier, password_key: password})
        if response.status_code != 200:
            raise LoginError(f"로그인 HTTP {response.status_code}")
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise LoginError("로그인 응답의 success가 true가 아닙니다.")
        data = payload.get("data")
        token = data.get("accessToken") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise LoginError("응답 data.accessToken이 없습니다.")
        token = re.sub(r"^Bearer\s+", "", token.strip(), flags=re.I)
        if "\r" in token or "\n" in token:
            raise LoginError("올바르지 않은 토큰 형식입니다.")
        return token
    except httpx.HTTPError as exc:
        raise LoginError(f"로그인 연결 실패: {type(exc).__name__}") from None
    except (json.JSONDecodeError, ValueError) as exc:
        raise LoginError("로그인 응답을 JSON으로 해석할 수 없습니다.") from None


def needs_user_token(endpoint) -> bool:
    auth = endpoint.request.get("auth") or {}
    if not isinstance(auth, dict) or auth.get("type") != "bearer":
        return False
    bearer = auth.get("bearer") or []
    return any(item.get("key") == "token" and item.get("value") == "{{userAccessToken}}"
               for item in bearer if isinstance(item, dict))

def user_login(base_url: str, email: str, password: str, *,
               timeout: float = 20, verify_ssl: bool = True,
               config: dict | None = None) -> str:
    return login_tokens("USER", base_url, email, password, timeout=timeout, verify_ssl=verify_ssl, config=config)[0]


def admin_login(base_url: str, admin_id: str, password: str, *,
                timeout: float = 20, verify_ssl: bool = True,
                config: dict | None = None) -> str:
    return login_tokens("ADMIN", base_url, admin_id, password, timeout=timeout, verify_ssl=verify_ssl, config=config)[0]


def needs_admin_token(endpoint) -> bool:
    auth = endpoint.request.get("auth") or {}
    if not isinstance(auth, dict) or auth.get("type") != "bearer":
        return False
    bearer = auth.get("bearer") or []
    return any(item.get("key") == "token" and item.get("value") == "{{adminAccessToken}}"
               for item in bearer if isinstance(item, dict))

REFRESH_ENDPOINTS = {
    "USER": "/api/auth/refresh",
    "ADMIN": "/api/backoffice/auth/refresh",
}


def _tokens_from_response(response, *, require_refresh=False, paths=None):
    if response.status_code != 200:
        raise LoginError(f"인증 API HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError:
        raise LoginError("인증 API의 응답이 JSON이 아닙니다.") from None
    if not isinstance(data, dict) or data.get("success") is not True:
        raise LoginError("인증 API의 success가 true가 아닙니다.")
    result = data.get("data")
    if not isinstance(result, dict):
        raise LoginError("인증 API에 data 객체가 없습니다.")
    if paths:
        from .json_paths import find_path
        found, access = find_path(data, paths["access_path"])
        if not found:
            access = None
        found, refresh = find_path(data, paths["refresh_path"])
        if not found:
            refresh = None
    else:
        access = result.get("accessToken")
        refresh = result.get("refreshToken")
    if not isinstance(access, str) or not access.strip():
        raise LoginError("인증 API에 Access Token이 없습니다.")
    access = re.sub(r"^Bearer\s+", "", access.strip(), flags=re.I)
    if isinstance(refresh, str):
        refresh = re.sub(r"^Bearer\s+", "", refresh.strip(), flags=re.I)
    else:
        refresh = None
    if require_refresh and not refresh:
        raise LoginError("로그인 응답에 Refresh Token이 없습니다.")
    if any("\\r" in v or "\\n" in v for v in (access, refresh or "")):
        raise LoginError("토큰 형식이 올바르지 않습니다.")
    return access, refresh


def login_tokens(profile: str, base_url: str, identifier: str, password: str, *,
                 timeout: float = 20, verify_ssl: bool = True,
                 config: dict | None = None,
                 token_paths: dict | None = None) -> tuple[str, str | None]:
    """Authenticate and keep both tokens in memory; never persist token values."""
    if profile not in DEFAULT_LOGIN_CONFIGS:
        raise LoginError("알 수 없는 로그인 유형입니다.")
    if not base_url.startswith(("http://", "https://")):
        raise LoginError("baseUrl은 HTTP(S) 주소여야 합니다.")
    if not identifier or not password:
        raise LoginError("로그인 계정정보를 입력하세요.")
    cfg = validate_login_config(config or DEFAULT_LOGIN_CONFIGS[profile])
    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.post(base_url.rstrip("/") + cfg["endpoint"],
                                   json={cfg["identifier_key"]: identifier,
                                         cfg["password_key"]: password})
        return _tokens_from_response(response, paths=token_paths)
    except httpx.HTTPError as exc:
        raise LoginError(f"로그인 연결 실패: {type(exc).__name__}") from None


def refresh_tokens(profile: str, base_url: str, refresh_token: str, *,
                   timeout: float = 20, verify_ssl: bool = True,
                   endpoint: str | None = None,
                   token_paths: dict | None = None) -> tuple[str, str]:
    """Use refreshToken body; retain the previous refresh token if not rotated."""
    if profile not in REFRESH_ENDPOINTS or not refresh_token:
        raise LoginError("Refresh Token을 사용할 수 없습니다.")
    if not base_url.startswith(("http://", "https://")):
        raise LoginError("baseUrl은 HTTP(S) 주소여야 합니다.")
    try:
        path = endpoint or REFRESH_ENDPOINTS[profile]
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or "://" in path or "?" in path or "#" in path:
            raise LoginError("Refresh Endpoint 형식이 올바르지 않습니다.")
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.post(base_url.rstrip("/") + path,
                                   json={"refreshToken": refresh_token})
        access, rotated = _tokens_from_response(response, paths=token_paths)
        return access, rotated or refresh_token
    except httpx.HTTPError as exc:
        raise LoginError(f"토큰 갱신 연결 실패: {type(exc).__name__}") from None
