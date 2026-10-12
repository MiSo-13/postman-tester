"""Aggregations are project-supplied, bounded, and skip pending runs."""
import pytest
from app.history_dashboard import build_dashboard


def run(key, status="COMPLETED"):
    return {"id": key, "name": key, "status": status, "started_at": key}


def item(name, status, ms=None, method="GET", url="https://example.test"):
    return {"endpoint_name": name, "method": method, "url": url,
            "status": status, "elapsed_ms": ms, "http_status": 200,
            "detail": "SECRET-NOT-IN-DASHBOARD"}


def test_failure_rate_skipped_and_timeline_order():
    runs = [run("new"), run("pending", "PENDING"), run("old")]
    data = {
        "old": [item("users", "PASS", 10), item("users", "SKIPPED"),
                item("admin", "ERROR", None)],
        "new": [item("users", "FAIL", 30), item("admin", "BLOCKED", None)]}
    dashboard = build_dashboard(runs, data)
    assert dashboard["runs"] == 2
    assert dashboard["executed"] == 4
    assert dashboard["failures"] == 3
    assert dashboard["skipped"] == 1
    assert dashboard["failure_rate"] == 75
    assert dashboard["avg_ms"] == 20
    assert [r["run_id"] for r in dashboard["timeline"]] == ["old", "new"]
    users = next(x for x in dashboard["apis"] if x["name"] == "users")
    assert users["failure_rate"] == 50
    assert users["avg_ms"] == 20
    assert "SECRET-NOT-IN-DASHBOARD" not in str(dashboard)


def test_all_skipped_has_no_division_by_zero():
    view = build_dashboard([run("one")], {"one": [item("x", "SKIPPED")]})
    assert view["failure_rate"] is None
    assert view["apis"][0]["failure_rate"] is None
    assert view["avg_ms"] is None


def test_run_limit_and_pending_exclusion():
    runs = [run("current"), run("waiting", "PENDING"), run("past")]
    view = build_dashboard(runs, {}, limit=1)
    assert view["runs"] == 1
    assert view["timeline"][0]["run_id"] == "current"
    for limit in (0, 201, -1):
        with pytest.raises(ValueError):
            build_dashboard([], {}, limit=limit)


def test_group_by_full_endpoint_identity():
    data = {"run": [item("users", "PASS", 7, url="https://a.test"),
                    item("users", "FAIL", 9, url="https://b.test")]}
    view = build_dashboard([run("run")], data)
    assert len(view["apis"]) == 2
