"""Ephemeral USER login. Credentials and tokens are not written to disk."""
import json
import re

import httpx



class LoginError(Exception):
    pass


def user_login(base_url: str, email: str, password: str, *,
               timeout: float = 20, verify_ssl: bool = True) -> str:
    if not base_url.startswith(("http://", "https://")):
        raise LoginError("baseUrl은 http 또는 https 주소여야 합니다.")
    if not email or not password:
        raise LoginError("이메일과 비밀번호를 입력하세요.")
    url = base_url.rstrip("/") + "/api/auth/login"
    try:
        with httpx.Client(timeout=timeout, verify=verify_ssl, follow_redirects=False) as client:
            response = client.post(url, json={"userEmail": email, "userPassword": password})
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
