from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.config import ATTEMPTS_FILE, LOGS_FILE, RECORDS_FILE, USERS_FILE
from app.core.exceptions import DataStoreError


class JsonStore:
    def __init__(self, path: Path, default_factory):
        self.path = path
        self.default_factory = default_factory
        self.ensure_exists()

    @classmethod
    def user_store(cls) -> "JsonStore":
        return cls(USERS_FILE, dict)

    @classmethod
    def record_store(cls) -> "JsonStore":
        return cls(RECORDS_FILE, list)

    @classmethod
    def log_store(cls) -> "JsonStore":
        return cls(LOGS_FILE, list)

    @classmethod
    def attempt_store(cls) -> "JsonStore":
        return cls(ATTEMPTS_FILE, dict)

    def ensure_exists(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.save(self.default_factory())

    def load(self):
        self.ensure_exists()
        try:
            with self.path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as exc:
            raise DataStoreError(f"El archivo {self.path.name} está corrupto.") from exc
        except OSError as exc:
            raise DataStoreError(f"No se pudo leer {self.path.name}.") from exc

    def save(self, data) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_fd, temp_name = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as temp_file:
                json.dump(data, temp_file, ensure_ascii=False, indent=4)
            os.replace(temp_name, self.path)
        except OSError as exc:
            raise DataStoreError(f"No se pudo guardar {self.path.name}.") from exc
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)
