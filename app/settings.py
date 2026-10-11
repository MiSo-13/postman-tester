"""Portable settings: keep setting.json beside the launched executable/script."""
import json
import os
import sys
from pathlib import Path


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class Settings:
    DEFAULTS = {
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

    def __init__(self, root: Path | None = None):
        self.root = (root or app_root()).resolve()
        self.path = self.root / "setting.json"
        self.values = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if self.path.is_file():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("setting.json의 최상위 구조는 객체여야 합니다.")
            self.values.update({key: value for key, value in data.items() if key in self.DEFAULTS})
        else:
            self.save()

    def save(self):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.values, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def set(self, key, value):
        if key not in self.DEFAULTS:
            raise KeyError(key)
        self.values[key] = value
        self.save()

    def data_path(self) -> Path:
        path = self.root / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path
