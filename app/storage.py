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
            CREATE TABLE IF NOT EXISTS project_base_urls (
                project_id TEXT PRIMARY KEY REFERENCES projects(id),
                base_url TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS imports (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                kind TEXT NOT NULL, filename TEXT NOT NULL,
                content TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS auth_configs (
                project_id TEXT NOT NULL REFERENCES projects(id),
                profile TEXT NOT NULL CHECK(profile IN ('USER','ADMIN')),
                endpoint TEXT NOT NULL,
                identifier_key TEXT NOT NULL,
                password_key TEXT NOT NULL,
                PRIMARY KEY(project_id, profile)
            );
            CREATE TABLE IF NOT EXISTS auth_profile_options (
                project_id TEXT NOT NULL REFERENCES projects(id),
                profile TEXT NOT NULL CHECK(profile IN ('USER','ADMIN')),
                config_json TEXT NOT NULL,
                PRIMARY KEY(project_id, profile)
            );
            CREATE TABLE IF NOT EXISTS response_extractions (
                project_id TEXT NOT NULL REFERENCES projects(id),
                endpoint_key TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                PRIMARY KEY(project_id, endpoint_key)
            );
            CREATE TABLE IF NOT EXISTS response_assertions (
                project_id TEXT NOT NULL REFERENCES projects(id),
                endpoint_key TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                PRIMARY KEY(project_id, endpoint_key)
            );
            CREATE TABLE IF NOT EXISTS request_overrides (
                project_id TEXT NOT NULL REFERENCES projects(id),
                endpoint_key TEXT NOT NULL,
                raw_body TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(project_id, endpoint_key)
            );
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                name TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_scenarios_project ON scenarios(project_id, name);
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
            CREATE TABLE IF NOT EXISTS run_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES test_runs(id),
                created_at TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_run_logs_run ON run_logs(run_id, id);
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES test_runs(id),
                format TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_project ON test_runs(project_id, started_at);
            CREATE INDEX IF NOT EXISTS idx_results_run ON run_results(run_id);
            CREATE INDEX IF NOT EXISTS idx_reports_run ON reports(run_id);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(run_results)")}
            if "retry_count" not in columns:
                db.execute("ALTER TABLE run_results ADD COLUMN retry_count INTEGER NOT NULL DEFAULT 0")

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

    def delete_project(self, project_id: str) -> list[str]:
        """Atomically delete project-owned DB records; return associated run IDs.

        Generated report directories are managed separately by the caller.
        """
        with self.connect() as db:
            if db.execute("SELECT 1 FROM projects WHERE id=?", (project_id,)).fetchone() is None:
                raise ValueError("삭제할 프로젝트가 존재하지 않습니다.")
            run_ids = [row["id"] for row in db.execute(
                "SELECT id FROM test_runs WHERE project_id=?", (project_id,))]
            for table in ("run_logs", "reports", "run_results"):
                db.execute(f"DELETE FROM {table} WHERE run_id IN "
                           "(SELECT id FROM test_runs WHERE project_id=?)", (project_id,))
            for table in ("test_runs", "imports", "auth_configs",
                          "auth_profile_options", "response_extractions",
                          "response_assertions", "request_overrides",
                          "scenarios", "project_base_urls"):
                db.execute(f"DELETE FROM {table} WHERE project_id=?", (project_id,))
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
        return run_ids

    def get_project_base_url(self, project_id: str):
        with self.connect() as db:
            row = db.execute("SELECT base_url FROM project_base_urls WHERE project_id=?", (project_id,)).fetchone()
            return row["base_url"] if row else None

    def save_project_base_url(self, project_id: str, base_url: str):
        from .auth_base_url import validate_base_url
        value = validate_base_url(base_url)
        with self.connect() as db:
            db.execute("""INSERT INTO project_base_urls(project_id, base_url) VALUES(?, ?)
                ON CONFLICT(project_id) DO UPDATE SET base_url=excluded.base_url""", (project_id, value))

    def save_import(self, project_id: str, kind: str, filename: str, document: dict) -> str:
        if kind == "environment":
            from .postman_auth_config import clean_environment
            document, _ = clean_environment(document)
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
                   status: str, http_status=None, elapsed_ms=None, detail="", retry_count=0):
        with self.connect() as db:
            db.execute(
                "INSERT INTO run_results (id, run_id, endpoint_name, method, url, "
                "status, http_status, elapsed_ms, detail, retry_count) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), run_id, name, method, url, status,
                 http_status, elapsed_ms, detail, retry_count))

    def runs(self, project_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM test_runs WHERE project_id=? ORDER BY started_at DESC", (project_id,))]

    def get_run(self, run_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM test_runs WHERE id=?", (run_id,)).fetchone()
            return dict(row) if row else None

    def results(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM run_results WHERE run_id=?", (run_id,))]

    def add_run_log(self, run_id: str, level: str, message: str):
        """Store bounded operational diagnostics, never request/response bodies."""
        if level not in ("INFO", "PASS", "FAIL", "ERROR", "BLOCKED", "SKIPPED"):
            raise ValueError("지원하지 않는 로그 수준입니다.")
        with self.connect() as db:
            db.execute(
                "INSERT INTO run_logs(run_id, created_at, level, message) VALUES(?,?,?,?)",
                (run_id, utc_now(), level, str(message)[:1000]))

    def run_logs(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT created_at,level,message FROM run_logs WHERE run_id=? ORDER BY id",
                (run_id,))]

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

    def get_auth_config(self, project_id: str, profile: str) -> dict | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT endpoint,identifier_key,password_key FROM auth_configs "
                "WHERE project_id=? AND profile=?", (project_id, profile)).fetchone()
            return dict(row) if row else None

    def save_auth_config(self, project_id: str, profile: str, config: dict) -> None:
        if profile not in ("USER", "ADMIN"):
            raise ValueError("알 수 없는 인증 프로필입니다.")
        from .user_auth import validate_login_config
        validated = validate_login_config(config)
        with self.connect() as db:
            db.execute("""
                INSERT INTO auth_configs (project_id,profile,endpoint,identifier_key,password_key)
                VALUES (?,?,?,?,?)
                ON CONFLICT(project_id,profile) DO UPDATE SET
                  endpoint=excluded.endpoint,
                  identifier_key=excluded.identifier_key,
                  password_key=excluded.password_key
            """, (project_id, profile, validated["endpoint"],
                  validated["identifier_key"], validated["password_key"]))

    def get_auth_profile_options(self, project_id: str, profile: str) -> dict:
        with self.connect() as db:
            row = db.execute(
                "SELECT config_json FROM auth_profile_options WHERE project_id=? AND profile=?",
                (project_id, profile)).fetchone()
            return json.loads(row["config_json"]) if row else {}

    def save_auth_profile_options(self, project_id: str, profile: str, options: dict):
        if profile not in ("USER", "ADMIN"):
            raise ValueError("지원하지 않는 인증 유형")
        from .auth_profile import validate_profile_options
        checked = validate_profile_options(options)
        with self.connect() as db:
            db.execute("""INSERT INTO auth_profile_options(project_id,profile,config_json)
                VALUES(?,?,?) ON CONFLICT(project_id,profile) DO UPDATE SET
                config_json=excluded.config_json""",
                (project_id, profile, json.dumps(checked, ensure_ascii=False)))

    def get_response_assertions(self, project_id: str, endpoint_key: str) -> list:
        with self.connect() as db:
            row = db.execute(
                "SELECT rules_json FROM response_assertions WHERE project_id=? AND endpoint_key=?",
                (project_id, endpoint_key)).fetchone()
            return json.loads(row["rules_json"]) if row else []

    def save_response_assertions(self, project_id: str, endpoint_key: str, rules: list):
        from .assertions import validate_rules
        rules = validate_rules(rules)
        with self.connect() as db:
            db.execute("""
                INSERT INTO response_assertions(project_id,endpoint_key,rules_json)
                VALUES(?,?,?)
                ON CONFLICT(project_id,endpoint_key) DO UPDATE SET
                    rules_json=excluded.rules_json
            """, (project_id, endpoint_key, json.dumps(rules, ensure_ascii=False)))

    def get_response_extractions(self, project_id: str, endpoint_key: str) -> list:
        with self.connect() as db:
            row = db.execute(
                "SELECT rules_json FROM response_extractions WHERE project_id=? AND endpoint_key=?",
                (project_id, endpoint_key)).fetchone()
            return json.loads(row["rules_json"]) if row else []

    def save_response_extractions(self, project_id: str, endpoint_key: str, rules: list):
        from .extractions import validate_extractions
        rules = validate_extractions(rules)
        with self.connect() as db:
            db.execute("""
                INSERT INTO response_extractions(project_id, endpoint_key, rules_json)
                VALUES (?,?,?)
                ON CONFLICT(project_id,endpoint_key) DO UPDATE SET
                    rules_json=excluded.rules_json
            """, (project_id, endpoint_key, json.dumps(rules, ensure_ascii=False)))

    def scenarios(self, project_id: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM scenarios WHERE project_id=? ORDER BY name, created_at",
                (project_id,))]

    def save_scenario(self, project_id: str, name: str, steps: list, scenario_id: str | None = None) -> str:
        from .scenarios import validate_steps
        steps = validate_steps(steps)
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
            raise ValueError("시나리오 이름은 1~100자여야 합니다.")
        if scenario_id is None:
            scenario_id = str(uuid.uuid4())
            with self.connect() as db:
                db.execute(
                    "INSERT INTO scenarios VALUES(?,?,?,?,?,?)",
                    (scenario_id, project_id, name.strip(),
                     json.dumps(steps), utc_now(), utc_now()))
        else:
            with self.connect() as db:
                cursor = db.execute(
                    "UPDATE scenarios SET name=?, steps_json=?, updated_at=? "
                    "WHERE id=? AND project_id=?",
                    (name.strip(), json.dumps(steps), utc_now(), scenario_id, project_id))
                if cursor.rowcount != 1:
                    raise ValueError("시나리오가 없거나 다른 프로젝트에 속합니다.")
        return scenario_id

    def delete_scenario(self, project_id: str, scenario_id: str):
        with self.connect() as db:
            db.execute("DELETE FROM scenarios WHERE id=? AND project_id=?", (scenario_id, project_id))

    def results_for_runs(self, project_id: str, run_ids: list[str]) -> dict[str, list[dict]]:
        """Read several histories with one SQL query, scoped to owning project."""
        if not run_ids:
            return {}
        if len(run_ids) > 200:
            raise ValueError("최대 200회 실행 이력만 조회할 수 있습니다.")
        ids = list(dict.fromkeys(run_ids))
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as db:
            rows = db.execute(
                "SELECT rr.*, rr.run_id FROM run_results rr "
                "JOIN test_runs tr ON tr.id = rr.run_id "
                f"WHERE tr.project_id = ? AND rr.run_id IN ({placeholders}) "
                "ORDER BY rr.rowid",
                [project_id, *ids]).fetchall()
        result = {identifier: [] for identifier in ids}
        for row in rows:
            result[row["run_id"]].append(dict(row))
        return result
