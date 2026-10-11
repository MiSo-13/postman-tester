"""Persistent projects, imported definitions and run history."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.db_path = root / "app.db"
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imports (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                kind TEXT NOT NULL, filename TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS request_overrides (
                project_id TEXT NOT NULL REFERENCES projects(id),
                endpoint_key TEXT NOT NULL,
                raw_body TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, endpoint_key)
            );
            CREATE TABLE IF NOT EXISTS test_runs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL, status TEXT NOT NULL,
                started_at TEXT NOT NULL, finished_at TEXT
            );
            CREATE TABLE IF NOT EXISTS run_results (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES test_runs(id),
                endpoint_name TEXT NOT NULL, method TEXT NOT NULL, url TEXT NOT NULL,
                status TEXT NOT NULL, http_status INTEGER,
                elapsed_ms REAL, detail TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES test_runs(id),
                format TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_project ON test_runs(project_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_results_run ON run_results(run_id);
            CREATE INDEX IF NOT EXISTS idx_reports_run ON reports(run_id);
            """)

    def connect(self):
        db = sqlite3.connect(self.db_path)
        db.execute("PRAGMA foreign_keys=ON")
        db.row_factory = sqlite3.Row
        return db

    def create_project(self, name: str) -> str:
        if not name.strip():
            raise ValueError("프로젝트 이름을 입력하세요.")
        identifier = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO projects VALUES(?,?,?)", (identifier, name.strip(), utc_now()))
        return identifier

    def projects(self) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM projects ORDER BY created_at")]

    def save_import(self, project_id: str, kind: str, filename: str, document: dict) -> str:
        identifier = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO imports VALUES(?,?,?,?,?,?)",
                (identifier, project_id, kind, filename, json.dumps(document, ensure_ascii=False), utc_now()))
        return identifier

    def latest_import(self, project_id: str, kind: str):
        with self.connect() as db:
            row = db.execute("""SELECT * FROM imports WHERE project_id=? AND kind=?
                ORDER BY created_at DESC, rowid DESC LIMIT 1""", (project_id, kind)).fetchone()
            return dict(row) if row else None

    def create_run(self, project_id: str, name: str) -> str:
        identifier = str(uuid.uuid4())
        with self.connect() as db:
            db.execute("INSERT INTO test_runs VALUES(?,?,?,?,?,NULL)",
                (identifier, project_id, name, "PENDING", utc_now()))
        return identifier

    def finish_run(self, run_id: str, status: str):
        with self.connect() as db:
            db.execute("UPDATE test_runs SET status=?, finished_at=? WHERE id=?",
                (status, utc_now(), run_id))

    def add_result(self, run_id: str, name: str, method: str, url: str,
                   status: str, http_status=None, elapsed_ms=None, detail=""):
        with self.connect() as db:
            db.execute("INSERT INTO run_results VALUES(?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), run_id, name, method, url, status, http_status, elapsed_ms, detail))

    def runs(self, project_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM test_runs WHERE project_id=? ORDER BY started_at DESC", (project_id,))]

    def results(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM run_results WHERE run_id=?", (run_id,))]

    def save_report(self, run_id: str, fmt: str, path: Path):
        with self.connect() as db:
            db.execute("INSERT INTO reports VALUES(?,?,?,?,?)",
                       (str(uuid.uuid4()), run_id, fmt, str(path.resolve()), utc_now()))

    def reports(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM reports WHERE run_id=?", (run_id,))]

    def get_request_override(self, project_id: str, endpoint_key: str) -> str | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT raw_body FROM request_overrides WHERE project_id=? AND endpoint_key=?",
                (project_id, endpoint_key)).fetchone()
            return row["raw_body"] if row else None

    def save_request_override(self, project_id: str, endpoint_key: str, body: str) -> None:
        with self.connect() as db:
            db.execute("""
                INSERT INTO request_overrides(project_id,endpoint_key,raw_body,updated_at)
                VALUES(?,?,?,?)
                ON CONFLICT(project_id,endpoint_key) DO UPDATE SET
                    raw_body=excluded.raw_body, updated_at=excluded.updated_at
            """, (project_id, endpoint_key, body, utc_now()))

    def remove_request_override(self, project_id: str, endpoint_key: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM request_overrides WHERE project_id=? AND endpoint_key=?",
                       (project_id, endpoint_key))
