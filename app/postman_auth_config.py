"""Discover USER/ADMIN auth routes from imported Postman Collection safely."""
import json
from .request_overrides import strip_json_comments
from .user_auth import DEFAULT_LOGIN_CONFIGS, validate_login_config, REFRESH_ENDPOINTS

TOKEN_NAMES = {"USER": "userAccessToken", "ADMIN": "adminAccessToken"}
SECRETS = {"userAccessToken", "userRefreshToken", "adminAccessToken", "adminRefreshToken"}


def clean_environment(document):
    if not isinstance(document, dict) or not isinstance(document.get("values"), list):
        raise ValueError("올바른 Postman Environment JSON이 아닙니다.")
    safe = dict(document)
    safe["values"] = []
    variables = {}
    for item in document["values"]:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            continue
        copied = dict(item)
        key = item["key"]
        secret = copied.get("type") == "secret" or key in SECRETS
        if secret:
            copied["value"] = ""
        safe["values"].append(copied)
        if item.get("enabled", True) and not secret:
            variables[key] = item.get("value", "")
    return safe, variables


def discover_auth(endpoints):
    """Use explicit login/refresh route patterns; never execute Postman scripts."""
    login = {}
    refresh = {}
    for endpoint in endpoints:
        if endpoint.method != "POST":
            continue
        url = endpoint.url
        if not url.startswith("{{baseUrl}}/"):
            continue
        route = url[len("{{baseUrl}}"):]
        if "?" in route or "#" in route:
            continue
        for profile, default in DEFAULT_LOGIN_CONFIGS.items():
            if route == default["endpoint"] or (
                route.endswith("/login") and
                (("backoffice" in route or "admin" in route) == (profile == "ADMIN"))):
                body = endpoint.request.get("body") or {}
                if body.get("mode") != "raw":
                    continue
                try:
                    parsed = json.loads(strip_json_comments(body.get("raw", "")))
                except (ValueError, TypeError):
                    continue
                if not isinstance(parsed, dict):
                    continue
                keys = list(parsed)
                if default["identifier_key"] in parsed and default["password_key"] in parsed:
                    identifier, password = default["identifier_key"], default["password_key"]
                elif len(keys) == 2:
                    password_keys = [k for k in keys if "pass" in k.lower() or k.lower().endswith("pw")]
                    if len(password_keys) != 1:
                        continue
                    password = password_keys[0]
                    identifier = next(k for k in keys if k != password)
                else:
                    continue
                try:
                    cfg = validate_login_config({"endpoint": route,
                                                 "identifier_key": identifier,
                                                 "password_key": password})
                except ValueError:
                    continue
                if profile in login and login[profile] != cfg:
                    login[profile] = None
                elif profile not in login:
                    login[profile] = cfg
            if route == REFRESH_ENDPOINTS[profile] or (
                route.endswith("/refresh") and
                (("backoffice" in route or "admin" in route) == (profile == "ADMIN"))):
                if profile in refresh and refresh[profile] != route:
                    refresh[profile] = None
                else:
                    refresh[profile] = route
    return login, refresh
