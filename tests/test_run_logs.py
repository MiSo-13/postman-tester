"""Run log persistence and project isolation regression tests."""
from app.storage import Storage


def test_run_logs_survive_storage_reopen(tmp_path):
    db = Storage(tmp_path)
    project = db.create_project("one")
    run_id = db.create_run(project, "run")
    db.add_run_log(run_id, "INFO", "테스트 시작")
    db.add_run_log(run_id, "ERROR", "USER 로그인: HTTP 401")
    logs = Storage(tmp_path).run_logs(run_id)
    assert [row["level"] for row in logs] == ["INFO", "ERROR"]
    assert "401" in logs[-1]["message"]
    assert all(row["created_at"] for row in logs)


def test_project_deletion_removes_only_owned_logs(tmp_path):
    db = Storage(tmp_path)
    first = db.create_project("first")
    second = db.create_project("second")
    a = db.create_run(first, "a")
    b = db.create_run(second, "b")
    db.add_run_log(a, "ERROR", "first only")
    db.add_run_log(b, "PASS", "second only")
    db.delete_project(first)
    assert db.run_logs(a) == []
    assert db.run_logs(b)[0]["message"] == "second only"


def test_log_level_and_message_limit(tmp_path):
    db = Storage(tmp_path)
    project = db.create_project("p")
    run = db.create_run(project, "r")
    db.add_run_log(run, "ERROR", "x" * 2000)
    assert len(db.run_logs(run)[0]["message"]) == 1000
