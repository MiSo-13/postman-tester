"""Postman v2.1 auth precedence and runner integration tests."""
import json
from pathlib import Path
from unittest.mock import patch

import httpx

from app.postman import parse_collection, endpoints_from_document
from app.runner import execute
from app.user_auth import needs_admin_token, needs_user_token


def bearer(variable):
    return {"type": "bearer", "bearer": [{"key": "token", "value": "{{" + variable + "}}"}]}


def collection():
    return {
        "info": {"name": "auth inheritance"},
        "auth": bearer("userAccessToken"),
        "item": [
            {"name": "root", "request": {"method": "GET", "url": "https://example.test/root"}},
            {"name": "folder", "auth": bearer("adminAccessToken"), "item": [
                {"name": "inherited", "request": {"method": "GET", "url": "https://example.test/admin"}},
                {"name": "explicit noauth", "request": {"method": "GET",
                    "url": "https://example.test/public", "auth": {"type": "noauth"}}},
                {"name": "explicit user", "request": {"method": "GET",
                    "url": "https://example.test/user", "auth": bearer("userAccessToken")}},
                {"name": "nested", "item": [
                    {"name": "nested admin", "request": {"method": "GET", "url": "https://example.test/nested"}},
                ]},
            ]},
        ],
    }


def test_inheritance_precedence_and_explicit_noauth(tmp_path):
    path = tmp_path / "collection.json"
    path.write_text(json.dumps(collection()), encoding="utf-8")
    _, endpoints = parse_collection(path)
    a = {e.name: e for e in endpoints}
    assert needs_user_token(a["root"])
    assert needs_admin_token(a["inherited"])
    assert needs_admin_token(a["nested admin"])
    assert needs_user_token(a["explicit user"])
    assert not needs_user_token(a["explicit noauth"])
    assert not needs_admin_token(a["explicit noauth"])
    assert "auth" not in collection()["item"][0]["request"]


def test_persisted_collection_reloads_inherited_auth():
    endpoints = endpoints_from_document(collection())
    assert needs_admin_token(next(e for e in endpoints if e.name == "nested admin"))


def test_runner_uses_inherited_admin_and_respects_noauth():
    api = {e.name: e for e in endpoints_from_document(collection())}
    captured = []
    def handler(request):
        captured.append((request.url.path, request.headers.get("authorization")))
        return httpx.Response(200)
    with patch("app.runner.httpx.Client", side_effect=lambda **kwargs: httpx.Client(
            transport=httpx.MockTransport(handler), **kwargs)):
        assert execute(api["inherited"], {}, admin_access_token="secret-admin")["status"] == "PASS"
        assert execute(api["explicit noauth"], {}, admin_access_token="secret-admin")["status"] == "PASS"
        assert execute(api["root"], {}, user_access_token="secret-user")["status"] == "PASS"
    assert captured == [
        ("/admin", "Bearer secret-admin"),
        ("/public", None),
        ("/root", "Bearer secret-user"),
    ]


def test_unknown_inherited_auth_fails_closed():
    doc = collection()
    doc["auth"] = {"type": "basic", "basic": []}
    first = endpoints_from_document(doc)[0]
    assert execute(first, {})["status"] == "BLOCKED"
