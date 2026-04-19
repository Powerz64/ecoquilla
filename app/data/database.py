from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from app.config import ATTEMPTS_FILE, DB_PATH, LOGS_FILE, RECORDS_FILE, USERS_FILE
from app.core.exceptions import DataStoreError
from app.core.utils import now_timestamp, only_upper
from app.core.validators import normalize_record


class SQLiteDatabase:
    """Manage SQLite connection lifecycle, schema creation, and JSON migration."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        json_sources: dict[str, Path] | None = None,
        auto_migrate: bool = True,
    ):
        self.path = path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.auto_migrate = auto_migrate
        self.json_sources = self._resolve_json_sources(json_sources)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def transaction(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception as exc:  # pragma: no cover - thin adapter
            connection.rollback()
            if isinstance(exc, DataStoreError):
                raise
            if isinstance(exc, sqlite3.Error):
                raise DataStoreError(f"Error en SQLite: {exc}") from exc
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    full_name TEXT NOT NULL DEFAULT '',
                    email TEXT NOT NULL DEFAULT '',
                    last_access TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    usuario TEXT NOT NULL,
                    registrado TEXT NOT NULL,
                    residuo TEXT NOT NULL,
                    zona TEXT NOT NULL,
                    direccion TEXT NOT NULL,
                    dia TEXT NOT NULL,
                    peso_kg REAL NOT NULL,
                    cantidad REAL NOT NULL,
                    estado TEXT NOT NULL,
                    resultado TEXT NOT NULL,
                    fecha TEXT NOT NULL,
                    creado_por TEXT NOT NULL,
                    notas TEXT NOT NULL DEFAULT '',
                    modificado_por TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT NOT NULL,
                    user TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL DEFAULT '',
                    migration_id TEXT,
                    migration_key TEXT
                );

                CREATE TABLE IF NOT EXISTS login_attempts (
                    username TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    blocked_until TEXT NOT NULL DEFAULT '',
                    client_id TEXT NOT NULL DEFAULT '',
                    device_info TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    client_id TEXT NOT NULL DEFAULT '',
                    device_info TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (username) REFERENCES users(username)
                );

                CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_records_fecha ON records(fecha);
                CREATE INDEX IF NOT EXISTS idx_records_usuario ON records(usuario);
                CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
                """
            )

        self._ensure_compatible_schema()
        self._ensure_meta_defaults()
        if self.auto_migrate:
            self.migrate_json_if_needed()

    def execute(self, query: str, parameters: tuple | dict = ()) -> None:
        with self.transaction() as connection:
            connection.execute(query, parameters)

    def fetchone(self, query: str, parameters: tuple | dict = ()) -> dict | None:
        with self.transaction() as connection:
            row = connection.execute(query, parameters).fetchone()
            return dict(row) if row else None

    def fetchall(self, query: str, parameters: tuple | dict = ()) -> list[dict]:
        with self.transaction() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return [dict(row) for row in rows]

    def executemany(self, query: str, rows: list[tuple] | list[dict]) -> None:
        if not rows:
            return
        with self.transaction() as connection:
            connection.executemany(query, rows)

    def meta_get(self, key: str) -> str | None:
        row = self.fetchone("SELECT value FROM app_meta WHERE key = ?", (key,))
        return row["value"] if row else None

    def meta_set(self, key: str, value: str) -> None:
        self.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )

    def migrate_json_if_needed(self) -> None:
        if self.meta_get("json_migration_completed") == "1":
            return

        previous_in_progress_id = self._get_in_progress_migration_id()
        previous_failure_id = self.meta_get("json_migration_last_failure_id") or ""
        migration_id = str(uuid4())
        self._mark_migration_started(migration_id)

        if previous_in_progress_id or previous_failure_id:
            previous_reference = previous_in_progress_id or previous_failure_id
            retry_reason = (
                "Se detecto una migracion previa interrumpida."
                if previous_in_progress_id
                else "Se detecto una migracion previa fallida."
            )
            self._write_migration_log(
                level="WARNING",
                action="MIGRATION RETRY",
                detail=(
                    f"{retry_reason} "
                    f"Anterior={previous_reference}. Nuevo intento={migration_id}."
                ),
                migration_id=migration_id,
                phase="retry",
            )

        self._write_migration_log(
            level="INFO",
            action="MIGRATION START",
            detail="Iniciando migracion JSON -> SQLite.",
            migration_id=migration_id,
            phase="start",
        )

        try:
            users = self._load_json(self.json_sources["users"], {})
            records = self._load_json(self.json_sources["records"], [])
            logs = self._load_json(self.json_sources["logs"], [])
            attempts = self._load_json(self.json_sources["login_attempts"], {})

            normalized_records = [normalize_record(raw_record) for raw_record in records]
            log_rows = [
                self._build_log_payload(log, index)
                for index, log in enumerate(logs, start=1)
            ]
            expected = {
                "users": [only_upper(username) for username in users.keys()],
                "records": [record["id"] for record in normalized_records],
                "logs": [row["migration_key"] for row in log_rows],
                "login_attempts": [only_upper(username) for username in attempts.keys()],
            }

            with self.transaction() as connection:
                if users:
                    now = now_timestamp()
                    user_rows = []
                    for username, data in users.items():
                        user_rows.append(
                            (
                                only_upper(username),
                                data.get("password", ""),
                                data.get("rol", "OPERADOR"),
                                1 if data.get("activo", True) else 0,
                                data.get("nombre_completo", ""),
                                data.get("email", ""),
                                data.get("ultimo_acceso", ""),
                                now,
                                now,
                            )
                        )
                    connection.executemany(
                        """
                        INSERT INTO users(
                            username, password_hash, role, active, full_name, email,
                            last_access, created_at, updated_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            password_hash = excluded.password_hash,
                            role = excluded.role,
                            active = excluded.active,
                            full_name = excluded.full_name,
                            email = excluded.email,
                            last_access = excluded.last_access,
                            updated_at = excluded.updated_at
                        """,
                        user_rows,
                    )

                if normalized_records:
                    now = now_timestamp()
                    record_rows = []
                    for record in normalized_records:
                        record_rows.append(
                            (
                                record["id"],
                                record["usuario"],
                                record["registrado"],
                                record["residuo"],
                                record["zona"],
                                record["direccion"],
                                record["dia"],
                                float(record["peso_kg"]),
                                float(record["cantidad"]),
                                record["estado"],
                                record["resultado"],
                                record["fecha"],
                                record["creado_por"],
                                record["notas"],
                                record.get("modificado_por", ""),
                                now,
                                now,
                            )
                        )
                    connection.executemany(
                        """
                        INSERT INTO records(
                            id, usuario, registrado, residuo, zona, direccion, dia,
                            peso_kg, cantidad, estado, resultado, fecha,
                            creado_por, notas, modificado_por, created_at, updated_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            usuario = excluded.usuario,
                            registrado = excluded.registrado,
                            residuo = excluded.residuo,
                            zona = excluded.zona,
                            direccion = excluded.direccion,
                            dia = excluded.dia,
                            peso_kg = excluded.peso_kg,
                            cantidad = excluded.cantidad,
                            estado = excluded.estado,
                            resultado = excluded.resultado,
                            fecha = excluded.fecha,
                            creado_por = excluded.creado_por,
                            notas = excluded.notas,
                            modificado_por = excluded.modificado_por,
                            updated_at = excluded.updated_at
                        """,
                        record_rows,
                    )

                if log_rows:
                    connection.executemany(
                        """
                        INSERT INTO logs(
                            level, user, action, detail, timestamp, session_id, migration_id, migration_key
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(migration_key) DO UPDATE SET
                            level = excluded.level,
                            user = excluded.user,
                            action = excluded.action,
                            detail = excluded.detail,
                            timestamp = excluded.timestamp,
                            session_id = excluded.session_id,
                            migration_id = excluded.migration_id
                        """,
                        [
                            (
                                row["level"],
                                row["user"],
                                row["action"],
                                row["detail"],
                                row["timestamp"],
                                row["session_id"],
                                row["migration_id"],
                                row["migration_key"],
                            )
                            for row in log_rows
                        ],
                    )

                if attempts:
                    attempt_rows = []
                    for username, data in attempts.items():
                        attempt_rows.append(
                            (
                                only_upper(username),
                                int(data.get("count", 0)),
                                data.get("blocked_until", ""),
                                data.get("client_id", ""),
                                data.get("device_info", ""),
                                now_timestamp(),
                            )
                        )
                    connection.executemany(
                        """
                        INSERT INTO login_attempts(
                            username, count, blocked_until, client_id, device_info, updated_at
                        ) VALUES(?, ?, ?, ?, ?, ?)
                        ON CONFLICT(username) DO UPDATE SET
                            count = excluded.count,
                            blocked_until = excluded.blocked_until,
                            client_id = excluded.client_id,
                            device_info = excluded.device_info,
                            updated_at = excluded.updated_at
                        """,
                        attempt_rows,
                    )

                self._validate_migration(connection, expected)
                self._mark_migration_completed(connection, migration_id)

            self._write_migration_log(
                level="INFO",
                action="MIGRATION SUCCESS",
                detail=(
                    "Migracion JSON -> SQLite completada. "
                    f"Users: {len(expected['users'])}, "
                    f"Records: {len(expected['records'])}, "
                    f"Logs: {len(expected['logs'])}, "
                    f"LoginAttempts: {len(expected['login_attempts'])}."
                ),
                migration_id=migration_id,
                phase="success",
            )
        except Exception as exc:
            self._mark_migration_failed(migration_id)
            self._write_migration_log(
                level="ERROR",
                action="MIGRATION FAILURE",
                detail=f"Migracion JSON -> SQLite fallida: {exc}",
                migration_id=migration_id,
                phase="failure",
            )
            raise

    @staticmethod
    def _load_json(path: Path, default):
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataStoreError(f"El archivo legacy {path.name} esta corrupto.") from exc

    def _ensure_compatible_schema(self) -> None:
        with self.transaction() as connection:
            columns = self._get_table_columns(connection, "logs")
            self._write_schema_fix_log(
                connection,
                columns,
                action="SCHEMA FIX START",
                detail="Verificando compatibilidad de la tabla logs.",
            )

            added_columns: list[str] = []
            if "migration_key" not in columns:
                connection.execute("ALTER TABLE logs ADD COLUMN migration_key TEXT")
                added_columns.append("migration_key")
                columns.add("migration_key")
            if "migration_id" not in columns:
                connection.execute("ALTER TABLE logs ADD COLUMN migration_id TEXT")
                added_columns.append("migration_id")
                columns.add("migration_id")

            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_logs_migration_key
                    ON logs(migration_key)
                """
            )
            if added_columns:
                self._write_schema_fix_log(
                    connection,
                    columns,
                    action="SCHEMA FIX APPLIED",
                    detail=(
                        "Actualizacion de esquema aplicada a logs. "
                        f"Columnas agregadas: {', '.join(added_columns)}."
                    ),
                )
            else:
                self._write_schema_fix_log(
                    connection,
                    columns,
                    action="SCHEMA FIX SKIPPED",
                    detail="La tabla logs ya tenia las columnas de compatibilidad requeridas.",
                )

    def _ensure_meta_defaults(self) -> None:
        defaults = {
            "json_migration_in_progress": "0",
            "json_migration_current_id": "",
        }
        with self.transaction() as connection:
            for key, value in defaults.items():
                connection.execute(
                    """
                    INSERT INTO app_meta(key, value)
                    VALUES(?, ?)
                    ON CONFLICT(key) DO NOTHING
                    """,
                    (key, value),
                )

    def _get_in_progress_migration_id(self) -> str:
        if self.meta_get("json_migration_in_progress") != "1":
            return ""
        return self.meta_get("json_migration_current_id") or self.meta_get("json_migration_last_started_id") or ""

    def _mark_migration_started(self, migration_id: str) -> None:
        started_at = now_timestamp()
        self.meta_set("json_migration_in_progress", "1")
        self.meta_set("json_migration_current_id", migration_id)
        self.meta_set("json_migration_last_started_id", migration_id)
        self.meta_set("json_migration_started_at", started_at)

    def _mark_migration_completed(self, connection: sqlite3.Connection, migration_id: str) -> None:
        completed_at = now_timestamp()
        self._set_meta_in_connection(connection, "json_migration_completed", "1")
        self._set_meta_in_connection(connection, "json_migration_in_progress", "0")
        self._set_meta_in_connection(connection, "json_migration_current_id", "")
        self._set_meta_in_connection(connection, "json_migration_timestamp", completed_at)
        self._set_meta_in_connection(connection, "json_migration_last_success_id", migration_id)
        self._set_meta_in_connection(connection, "json_migration_last_failure_id", "")
        self._set_meta_in_connection(connection, "json_migration_last_failure_at", "")

    def _mark_migration_failed(self, migration_id: str) -> None:
        failed_at = now_timestamp()
        self.meta_set("json_migration_in_progress", "0")
        self.meta_set("json_migration_current_id", "")
        self.meta_set("json_migration_last_failure_id", migration_id)
        self.meta_set("json_migration_last_failure_at", failed_at)

    def _write_migration_log(
        self,
        *,
        level: str,
        action: str,
        detail: str,
        migration_id: str,
        phase: str,
    ) -> None:
        migration_key = self._build_migration_log_key(migration_id, phase)
        try:
            self.execute(
                """
                INSERT INTO logs(
                    level, user, action, detail, timestamp, session_id, migration_id, migration_key
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(migration_key) DO UPDATE SET
                    level = excluded.level,
                    user = excluded.user,
                    action = excluded.action,
                    detail = excluded.detail,
                    timestamp = excluded.timestamp,
                    session_id = excluded.session_id,
                    migration_id = excluded.migration_id
                """,
                (level, "SYSTEM", action, detail, now_timestamp(), "", migration_id, migration_key),
            )
        except Exception:
            pass

    @staticmethod
    def _build_migration_log_key(migration_id: str, phase: str) -> str:
        return f"migration:{migration_id}:{phase.lower()}"

    @staticmethod
    def _get_table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
        return {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

    def _write_schema_fix_log(
        self,
        connection: sqlite3.Connection,
        available_columns: set[str],
        *,
        action: str,
        detail: str,
    ) -> None:
        base_payload = {
            "level": "INFO",
            "user": "SYSTEM",
            "action": action,
            "detail": detail,
            "timestamp": now_timestamp(),
            "session_id": "",
            "migration_id": "",
            "migration_key": None,
        }
        insertable_columns = [
            column
            for column in (
                "level",
                "user",
                "action",
                "detail",
                "timestamp",
                "session_id",
                "migration_id",
                "migration_key",
            )
            if column in available_columns
        ]
        placeholders = ", ".join("?" for _ in insertable_columns)
        connection.execute(
            f"""
            INSERT INTO logs({", ".join(insertable_columns)})
            VALUES({placeholders})
            """,
            tuple(base_payload[column] for column in insertable_columns),
        )

    def _build_log_payload(self, log: dict, index: int) -> dict:
        timestamp = log.get("timestamp") or f"{log.get('fecha', '')}T{log.get('hora', '')}"
        level = "INFO"
        action = str(log.get("accion", "")).upper()
        detail = str(log.get("detalle", "")).upper()
        if "ERROR" in action or "ERROR" in detail:
            level = "ERROR"
        elif "FALLIDO" in action or "BLOQUEADO" in action:
            level = "WARNING"

        source = json.dumps(log, ensure_ascii=False, sort_keys=True)
        migration_key = f"legacy-log-{index}-{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
        return {
            "level": level,
            "user": only_upper(log.get("usuario", "")),
            "action": log.get("accion", ""),
            "detail": log.get("detalle", ""),
            "timestamp": timestamp,
            "session_id": "",
            "migration_id": "",
            "migration_key": migration_key,
        }

    def _validate_migration(self, connection: sqlite3.Connection, expected: dict[str, list[str]]) -> None:
        validations = {
            "users": self._count_matching(connection, "users", "username", expected["users"]),
            "records": self._count_matching(connection, "records", "id", expected["records"]),
            "logs": self._count_matching(connection, "logs", "migration_key", expected["logs"]),
            "login_attempts": self._count_matching(
                connection,
                "login_attempts",
                "username",
                expected["login_attempts"],
            ),
        }

        for table_name, actual_count in validations.items():
            expected_count = len(expected[table_name])
            if actual_count != expected_count:
                raise DataStoreError(
                    f"Validacion de migracion fallida para {table_name}: "
                    f"esperados={expected_count}, insertados={actual_count}."
                )

    @staticmethod
    def _count_matching(
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        values: list[str],
    ) -> int:
        if not values:
            return 0
        placeholders = ", ".join("?" for _ in values)
        row = connection.execute(
            f"SELECT COUNT(*) AS total FROM {table_name} WHERE {column_name} IN ({placeholders})",
            tuple(values),
        ).fetchone()
        return int(row["total"]) if row else 0

    @staticmethod
    def _resolve_json_sources(json_sources: dict[str, Path] | None) -> dict[str, Path]:
        sources = dict(json_sources or {})
        return {
            "users": Path(sources.get("users", USERS_FILE)),
            "records": Path(sources.get("records", RECORDS_FILE)),
            "logs": Path(sources.get("logs", LOGS_FILE)),
            "login_attempts": Path(sources.get("login_attempts", ATTEMPTS_FILE)),
        }

    @staticmethod
    def _set_meta_in_connection(connection: sqlite3.Connection, key: str, value: str) -> None:
        connection.execute(
            """
            INSERT INTO app_meta(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
