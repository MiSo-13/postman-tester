"""Persistent performance indicators and report safety tests."""
import sqlite3
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from app.performance_reports import percentile, performance_summary, export_performance_report
from app.retry_policy import RetryPolicy, execute_with_retries
from app.storage import Storage


def test_nearest_rank_percentile_and_missing_values():
    assert percentile([10, 20, 30, 40, 50], 50) == 30
    assert percentile([10, 20, 30, 40, 50], 95) == 50
    assert percentile([10, 20, 30, 40, 50], 99) == 50
    assert percentile([None, float("nan"), -2], 95) is None


def test_run_performance_summary_percentiles_and_rps():
    run = {"id": "r", "name": "test", "status": "COMPLETED",
           "started_at": "2026-10-12T00:00:00+00:00",
           "finished_at": "2026-10-12T00:00:02+00:00"}
    rows = [{"status": "PASS", "elapsed_ms": v, "retry_count": n}
            for v, n in ((10, 0), (20, 2), (30, 0), (40, 1))]
    rows.append({"status": "SKIPPED", "elapsed_ms": None, "retry_count": 0})
    result = performance_summary(run, rows)
    assert (result["p50_ms"], result["p95_ms"], result["p99_ms"]) == (20, 40, 40)
    assert result["rps"] == 2.0
    assert result["retries"] == 3
    assert result["skipped"] == 1


def test_storage_migration_preserves_old_rows(tmp_path):
    store = Storage(tmp_path)
    project = store.create_project("existing")
    run_id = store.create_run(project, "old")
    store.add_result(run_id, "old", "GET", "https://example.test", "PASS", 200, 7)
    with sqlite3.connect(store.db_path) as db:
        db.execute("ALTER TABLE run_results RENAME TO old_results")
        db.execute("""CREATE TABLE run_results (
            id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
            endpoint_name TEXT NOT NULL, method TEXT NOT NULL, url TEXT NOT NULL,
            status TEXT NOT NULL, http_status INTEGER, elapsed_ms REAL,
            detail TEXT NOT NULL DEFAULT '')""")
        db.execute("""INSERT INTO run_results
            (id,run_id,endpoint_name,method,url,status,http_status,elapsed_ms,detail)
            SELECT id,run_id,endpoint_name,method,url,status,http_status,elapsed_ms,detail
            FROM old_results""")
        db.execute("DROP TABLE old_results")
    reopened = Storage(tmp_path)
    rows = reopened.results(run_id)
    assert len(rows) == 1 and rows[0]["retry_count"] == 0
    reopened.add_result(run_id, "new", "GET", "https://example.test", "PASS",
                        200, 5, retry_count=2)
    assert reopened.results(run_id)[1]["retry_count"] == 2


def test_retry_callback_reports_real_attempts():
    attempts = []
    responses = iter([
        {"status": "FAIL", "http_status": 503},
        {"status": "PASS", "http_status": 200},
    ])
    endpoint = type("Endpoint", (), {"method": "GET"})()
    answer = execute_with_retries(
        lambda: next(responses), endpoint, RetryPolicy(retries=2),
        on_attempt=attempts.append)
    assert answer["status"] == "PASS"
    assert attempts == [1, 2]


def test_performance_reports_html_xlsx_and_persistence(tmp_path):
    store = Storage(tmp_path / "db")
    project = store.create_project("run")
    run_id = store.create_run(project, "=2+2<script>")
    store.add_result(run_id, "endpoint", "GET", "https://example.test",
                     "PASS", 200, 19, retry_count=2)
    store.finish_run(run_id, "COMPLETED")
    files = export_performance_report(store, run_id, tmp_path / "reports")
    assert len(files) == 2 and all(x.is_file() for x in files)
    ws = load_workbook(files[0])["Performance"]
    assert any(row[0] == "총 재시도 횟수" and row[1] == 2 for row in ws.values)
    html = files[1].read_text(encoding="utf-8")
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert len(store.reports(run_id)) == 2
