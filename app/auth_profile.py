"""Validated non-secret options for per-project Postman authentication profiles."""
from .json_paths import path_parts

DEFAULT_PATHS = {"access_path": "data.accessToken", "refresh_path": "data.refreshToken"}


def validate_profile_options(options):
    if not isinstance(options, dict):
        raise ValueError("인증 옵션은 JSON 객체여야 합니다.")
    checked = {}
    for field in ("access_path", "refresh_path"):
        value = options.get(field, DEFAULT_PATHS[field])
        path_parts(value)
        checked[field] = value
    return checked


def endpoint_login_choices(endpoints):
    """Candidates must be POST requests with a local baseUrl path."""
    choices = []
    for endpoint in endpoints:
        if (endpoint.method == "POST" and
                endpoint.url.startswith("{{baseUrl}}/") and
                "?" not in endpoint.url and "#" not in endpoint.url):
            choices.append((endpoint.name, endpoint.url[len("{{baseUrl}}"):]))
    return choices
