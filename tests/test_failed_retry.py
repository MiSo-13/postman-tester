"""Safe replay selection never reissues mutation requests."""
from types import SimpleNamespace

from app.retry import retry_candidates


def endpoint(name, method="GET", url="https://example.test/resource"):
    return SimpleNamespace(name=name, method=method, url=url, request={"header": []})


def result(name, method, status, url="https://example.test/resource"):
    return {"endpoint_name": name, "method": method,
            "status": status, "url": url}


def test_retries_only_failed_safe_methods():
    endpoints = [endpoint("get"), endpoint("create", "POST"),
                 endpoint("head", "HEAD"), endpoint("ok")]
    keys = ["a", "b", "c", "d"]
    saved = [result("get", "GET", "FAIL"),
             result("create", "POST", "FAIL"),
             result("head", "HEAD", "ERROR"),
             result("ok", "GET", "PASS"),
             result("get", "GET", "FAIL")]
    selected = retry_candidates(saved, endpoints, keys)
    assert [key for key, _ in selected] == ["a", "c"]


def test_unknown_and_ambiguous_matches_fail_closed():
    duplicated = [endpoint("same"), endpoint("same")]
    assert retry_candidates([result("same", "GET", "FAIL")],
                            duplicated, ["a", "b"]) == []
    assert retry_candidates([result("missing", "GET", "FAIL")],
                            duplicated, ["a", "b"]) == []


def test_never_replays_writes_even_if_failed():
    endpoints = [endpoint(method=m, name=m) for m in
                 ("POST", "PUT", "PATCH", "DELETE")]
    saved = [result(e.name, e.method, "ERROR") for e in endpoints]
    assert retry_candidates(saved, endpoints, list("abcd")) == []


def test_skipped_and_blocked_distinction():
    api = endpoint("read")
    assert retry_candidates([result("read", "GET", "SKIPPED")], [api], ["a"]) == []
    assert len(retry_candidates([result("read", "GET", "BLOCKED")], [api], ["a"])) == 1
