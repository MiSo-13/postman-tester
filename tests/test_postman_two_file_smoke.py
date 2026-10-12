"""Realistic Postman Collection + Environment smoke flow without a live server."""
import json

import httpx

from app.postman import endpoints_from_document, parse_collection
from app.postman_auth_config import clean_environment, discover_auth
from app.request_overrides import endpoint_key
from app.runner import execute
from app.user_auth import needs_admin_token, needs_user_token


def sample_collection():
    return {"info": {"schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
            "auth": {"type": "noauth"}, "item": [
                {"name": "인증 - Auth", "item": [
                    {"name": "로그인", "request": {"method": "POST", "url": {"raw": "{{baseUrl}}/api/auth/login"},
                       "body": {"mode": "raw", "raw": '{"userEmail":"sample", // example\n"userPassword":"example"}'}}},
                    {"name": "내 정보 조회", "request": {"method": "GET", "url": {"raw": "{{baseUrl}}/api/user/me"},
                       "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{userAccessToken}}"}]}}}]},
                {"name": "인증 - Admin Auth", "item": [
                    {"name": "관리자 로그인", "request": {"method": "POST", "url": {"raw": "{{baseUrl}}/api/backoffice/auth/login"},
                       "body": {"mode": "raw", "raw": '{"adminId":"admin","adminPw":"example"}'}}},
                    {"name": "관리자 정보", "request": {"method": "GET", "url": {"raw": "{{baseUrl}}/api/backoffice/auth/me"},
                       "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{adminAccessToken}}"}]}}}]}]}


def test_two_json_import_and_authenticated_read_flow(tmp_path):
    collection = sample_collection()
    source = tmp_path / "collection.json"
    source.write_text(json.dumps(collection, ensure_ascii=False), encoding="utf-8")
    document, parsed = parse_collection(source)
    assert parsed == endpoints_from_document(document)
    assert len(parsed) == 4
    assert needs_user_token(parsed[1]) and not needs_admin_token(parsed[1])
    assert needs_admin_token(parsed[3]) and not needs_user_token(parsed[3])
    login, refresh = discover_auth(parsed)
    assert login["USER"]["identifier_key"] == "userEmail"
    assert login["ADMIN"]["password_key"] == "adminPw"
    environment = {"values": [
        {"key": "baseUrl", "value": "https://api.example.test", "enabled": True},
        {"key": "userAccessToken", "value": "token-in-file", "type": "secret"}]}
    cleaned, vars_ = clean_environment(environment)
    assert "token-in-file" not in json.dumps(cleaned)
    assert vars_ == {"baseUrl": "https://api.example.test"}
    observed = []
    def handler(request):
        observed.append((request.url.path, request.headers.get("authorization")))
        return httpx.Response(200, json={"success": True, "data": {"id": 1}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        blocked = execute(parsed[1], vars_, client=client)
        user = execute(parsed[1], vars_, client=client, user_access_token="user-token")
        admin = execute(parsed[3], vars_, client=client, admin_access_token="admin-token")
    assert blocked["status"] == "BLOCKED"
    assert user["status"] == admin["status"] == "PASS"
    assert observed == [
        ("/api/user/me", "Bearer user-token"),
        ("/api/backoffice/auth/me", "Bearer admin-token")]
    assert endpoint_key(parsed[1]) != endpoint_key(parsed[3])


def test_memory_parser_does_not_touch_tempfile(tmp_path, monkeypatch):
    import tempfile
    monkeypatch.setattr(tempfile, "TemporaryDirectory", lambda: (_ for _ in ()).throw(AssertionError("unexpected temporary file")))
    endpoints = endpoints_from_document(sample_collection())
    assert len(endpoints) == 4
