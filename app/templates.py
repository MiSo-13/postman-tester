"""Importable, human-editable examples for people and AI tools."""
import json
from pathlib import Path

COLLECTION_EXAMPLE = {
    "info": {
        "name": "API 테스트 예제",
        "description": "Postman Collection v2.1 예시. 사람이 작성하거나 AI가 생성할 때 참고하세요.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "variable": [{"key": "baseUrl", "value": "http://localhost:8080"}],
    "item": [{
        "name": "인증",
        "item": [{
            "name": "로그인",
            "request": {
                "method": "POST",
                "header": [{"key": "Content-Type", "value": "application/json"}],
                "url": {"raw": "{{baseUrl}}/api/auth/login",
                        "host": ["{{baseUrl}}"], "path": ["api", "auth", "login"]},
                "body": {"mode": "raw", "raw": "{\n  \"username\": \"example\",\n  \"password\": \"change-me\"\n}",
                         "options": {"raw": {"language": "json"}}}
            },
            "response": [{
                "name": "성공 예제", "status": "OK", "code": 200,
                "body": "{\"success\": true, \"data\": {\"accessToken\": \"example-token\"}}"
            }]
        }, {
            "name": "상태 확인",
            "request": {"method": "GET", "url": "{{baseUrl}}/health"},
            "response": [{"name": "정상", "code": 200, "body": "{\"status\": \"UP\"}"}]
        }]
    }]
}
ENVIRONMENT_EXAMPLE = {
    "name": "Local Example",
    "values": [
        {"key": "baseUrl", "value": "http://localhost:8080", "enabled": True, "type": "default"},
        {"key": "userAccessToken", "value": "", "enabled": True, "type": "secret"}
    ],
    "_postman_variable_scope": "environment"
}
SETTING_EXAMPLE = {
    "schema_version": 1,
    "theme": "system",
    "last_project_id": None,
    "default_timeout_seconds": 20,
    "verify_ssl": True,
    "file_root": "data/uploads",
    "reports_directory": "data/reports",
    "response_max_bytes": 1048576,
    "dangerous_methods_enabled": False
}


def save_examples(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    examples = [
        ("postman_collection.example.json", COLLECTION_EXAMPLE),
        ("postman_environment.example.json", ENVIRONMENT_EXAMPLE),
        ("setting.example.json", SETTING_EXAMPLE),
    ]
    results = []
    for filename, content in examples:
        path = directory / filename
        path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append(path)
    return results
