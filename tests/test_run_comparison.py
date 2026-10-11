from app.run_comparison import compare_runs


def row(name, status, elapsed=20, method="GET", url="https://example.test/a", http=200):
    return {"endpoint_name": name, "status": status, "elapsed_ms": elapsed,
            "method": method, "url": url, "http_status": http, "detail": "never include"}


def test_recovered_regressed_and_unchanged():
    previous = [row("a", "FAIL", 20), row("b", "PASS", 11), row("c", "PASS", 9)]
    latest = [row("a", "PASS", 17), row("b", "ERROR", None), row("c", "PASS", 10)]
    result = compare_runs(previous, latest)
    assert [r["change"] for r in result] == ["RECOVERED", "REGRESSED", "UNCHANGED"]
    assert result[0]["delta_ms"] == -3
    assert result[1]["delta_ms"] is None
    assert all("detail" not in r for r in result)


def test_add_remove_and_duplicate_occurrences():
    before = [row("repeat", "PASS"), row("repeat", "FAIL"), row("old", "PASS")]
    after = [row("repeat", "FAIL"), row("new", "PASS")]
    result = compare_runs(before, after)
    assert [(r["name"], r["change"]) for r in result] == [
        ("new", "ADDED"), ("old", "REMOVED"),
        ("repeat", "REGRESSED"), ("repeat", "REMOVED")]


def test_empty_inputs():
    assert compare_runs([], []) == []
    assert compare_runs([], [row("new", "PASS")])[0]["change"] == "ADDED"
