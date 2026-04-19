from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.config import LOGIN_BLOCK_SECONDS, MAX_LOGIN_ATTEMPTS
from app.core.security import hash_password
from app.core.utils import (
    iso_to_display_date,
    iso_to_display_time,
    now_timestamp,
    only_upper,
    parse_bool,
)
from app.core.validators import normalize_record
from app.data.database import SQLiteDatabase


class LogRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def list_all(self, filter_text: str = "") -> list[dict]:
        query = """
            SELECT id, level, user, action, detail, timestamp, session_id
            FROM logs
        """
        parameters: tuple = ()
        if filter_text:
            query += """
                WHERE UPPER(user || ' ' || action || ' ' || detail || ' ' || timestamp || ' ' || level)
                LIKE ?
            """
            parameters = (f"%{filter_text.upper()}%",)
        query += " ORDER BY timestamp DESC, id DESC"
        rows = self.database.fetchall(query, parameters)
        return [self._to_public_log(row) for row in rows]

    def add(
        self,
        user: str,
        action: str,
        detail: str,
        *,
        level: str = "INFO",
        session_id: str = "",
    ) -> None:
        self.database.execute(
            """
            INSERT INTO logs(level, user, action, detail, timestamp, session_id)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (level, only_upper(user), action, detail, now_timestamp(), session_id),
        )

    @staticmethod
    def _to_public_log(row: dict) -> dict:
        return {
            "id": row["id"],
            "level": row["level"],
            "user": row["user"],
            "action": row["action"],
            "detail": row["detail"],
            "timestamp": row["timestamp"],
            "session_id": row.get("session_id", ""),
            "usuario": row["user"],
            "accion": row["action"],
            "detalle": row["detail"],
            "fecha": iso_to_display_date(row["timestamp"]),
            "hora": iso_to_display_time(row["timestamp"]),
        }


class UserRepository:
    DEFAULT_USERS = {
        "MIGUEL": {
            "password": "Miguel123",
            "rol": "ADMIN",
            "activo": True,
            "nombre_completo": "Miguel Cuello",
            "email": "admin@ecoquilla.com",
            "ultimo_acceso": "",
        },
        "USUARIO": {
            "password": "Usuario123",
            "rol": "OPERADOR",
            "activo": True,
            "nombre_completo": "Operador General",
            "email": "op@ecoquilla.com",
            "ultimo_acceso": "",
        },
    }

    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def list_all(self) -> dict[str, dict]:
        rows = self.database.fetchall(
            """
            SELECT username, password_hash, role, active, full_name, email, last_access
            FROM users
            ORDER BY username
            """
        )
        return {row["username"]: self._to_public_user(row) for row in rows}

    def save_all(self, users: dict) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM users")
            for username, data in users.items():
                connection.execute(
                    """
                    INSERT INTO users(
                        username, password_hash, role, active, full_name, email,
                        last_access, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        only_upper(username),
                        data.get("password", ""),
                        data.get("rol", "OPERADOR"),
                        1 if data.get("activo", True) else 0,
                        data.get("nombre_completo", ""),
                        data.get("email", ""),
                        data.get("ultimo_acceso", ""),
                        now_timestamp(),
                        now_timestamp(),
                    ),
                )

    def exists(self, username: str) -> bool:
        return self.get(username) is not None

    def get(self, username: str) -> dict | None:
        row = self.database.fetchone(
            """
            SELECT username, password_hash, role, active, full_name, email, last_access
            FROM users
            WHERE username = ?
            """,
            (only_upper(username),),
        )
        return self._to_public_user(row) if row else None

    def upsert(self, username: str, data: dict) -> None:
        username = only_upper(username)
        self.database.execute(
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
            (
                username,
                data.get("password", ""),
                data.get("rol", "OPERADOR"),
                1 if data.get("activo", True) else 0,
                data.get("nombre_completo", ""),
                data.get("email", ""),
                data.get("ultimo_acceso", ""),
                now_timestamp(),
                now_timestamp(),
            ),
        )

    def ensure_defaults(self) -> None:
        users = self.list_all()
        for username, data in self.DEFAULT_USERS.items():
            if username not in users:
                self.upsert(
                    username,
                    {
                        **data,
                        "password": hash_password(data["password"]),
                    },
                )

    @staticmethod
    def _to_public_user(row: dict | None) -> dict | None:
        if not row:
            return None
        return {
            "password": row["password_hash"],
            "rol": row["role"],
            "activo": parse_bool(row["active"]),
            "nombre_completo": row["full_name"],
            "email": row["email"],
            "ultimo_acceso": row["last_access"],
        }


class RecordRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def list_all(self) -> list[dict]:
        rows = self.database.fetchall(
            """
            SELECT id, usuario, registrado, residuo, zona, direccion, dia,
                   peso_kg, cantidad, estado, resultado, fecha,
                   creado_por, notas, modificado_por
            FROM records
            ORDER BY created_at ASC, id ASC
            """
        )
        return [normalize_record(row) for row in rows]

    def save_all(self, records: list[dict]) -> None:
        with self.database.transaction() as connection:
            connection.execute("DELETE FROM records")
            for record in records:
                normalized = normalize_record(record)
                connection.execute(
                    """
                    INSERT INTO records(
                        id, usuario, registrado, residuo, zona, direccion, dia,
                        peso_kg, cantidad, estado, resultado, fecha,
                        creado_por, notas, modificado_por, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["id"],
                        normalized["usuario"],
                        normalized["registrado"],
                        normalized["residuo"],
                        normalized["zona"],
                        normalized["direccion"],
                        normalized["dia"],
                        float(normalized["peso_kg"]),
                        float(normalized["cantidad"]),
                        normalized["estado"],
                        normalized["resultado"],
                        normalized["fecha"],
                        normalized["creado_por"],
                        normalized["notas"],
                        normalized.get("modificado_por", ""),
                        now_timestamp(),
                        now_timestamp(),
                    ),
                )

    def create(self, record: dict) -> None:
        normalized = normalize_record(record)
        self.database.execute(
            """
            INSERT INTO records(
                id, usuario, registrado, residuo, zona, direccion, dia,
                peso_kg, cantidad, estado, resultado, fecha,
                creado_por, notas, modificado_por, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["id"],
                normalized["usuario"],
                normalized["registrado"],
                normalized["residuo"],
                normalized["zona"],
                normalized["direccion"],
                normalized["dia"],
                float(normalized["peso_kg"]),
                float(normalized["cantidad"]),
                normalized["estado"],
                normalized["resultado"],
                normalized["fecha"],
                normalized["creado_por"],
                normalized["notas"],
                normalized.get("modificado_por", ""),
                now_timestamp(),
                now_timestamp(),
            ),
        )

    def update(self, record: dict) -> None:
        normalized = normalize_record(record)
        self.database.execute(
            """
            UPDATE records SET
                usuario = ?, registrado = ?, residuo = ?, zona = ?, direccion = ?,
                dia = ?, peso_kg = ?, cantidad = ?, estado = ?, resultado = ?,
                fecha = ?, creado_por = ?, notas = ?, modificado_por = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["usuario"],
                normalized["registrado"],
                normalized["residuo"],
                normalized["zona"],
                normalized["direccion"],
                normalized["dia"],
                float(normalized["peso_kg"]),
                float(normalized["cantidad"]),
                normalized["estado"],
                normalized["resultado"],
                normalized["fecha"],
                normalized["creado_por"],
                normalized["notas"],
                normalized.get("modificado_por", ""),
                now_timestamp(),
                normalized["id"],
            ),
        )

    def delete(self, record_id: str) -> None:
        self.database.execute("DELETE FROM records WHERE id = ?", (record_id,))


class LoginAttemptRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def blocked_seconds(self, username: str) -> int:
        row = self.database.fetchone(
            "SELECT blocked_until FROM login_attempts WHERE username = ?",
            (only_upper(username),),
        )
        blocked_until = row["blocked_until"] if row else ""
        if not blocked_until:
            return 0

        remaining = int((datetime.fromisoformat(blocked_until) - datetime.now()).total_seconds())
        if remaining <= 0:
            self.reset(username)
            return 0
        return remaining

    def register_failure(
        self,
        username: str,
        *,
        client_id: str = "",
        device_info: str = "",
    ) -> dict:
        username = only_upper(username)
        row = self.database.fetchone(
            """
            SELECT count, blocked_until
            FROM login_attempts
            WHERE username = ?
            """,
            (username,),
        ) or {"count": 0, "blocked_until": ""}

        count = int(row["count"]) + 1
        blocked = False
        blocked_seconds = 0
        blocked_until = row.get("blocked_until", "")
        if count >= MAX_LOGIN_ATTEMPTS:
            blocked = True
            blocked_seconds = LOGIN_BLOCK_SECONDS
            count = 0
            blocked_until = (datetime.now() + timedelta(seconds=LOGIN_BLOCK_SECONDS)).isoformat()

        self.database.execute(
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
            (username, count, blocked_until, client_id, device_info, now_timestamp()),
        )
        return {
            "blocked": blocked,
            "remaining_attempts": max(MAX_LOGIN_ATTEMPTS - count, 0),
            "blocked_seconds": blocked_seconds,
        }

    def reset(self, username: str) -> None:
        self.database.execute(
            """
            INSERT INTO login_attempts(
                username, count, blocked_until, client_id, device_info, updated_at
            ) VALUES(?, 0, '', '', '', ?)
            ON CONFLICT(username) DO UPDATE SET
                count = 0,
                blocked_until = '',
                updated_at = excluded.updated_at
            """,
            (only_upper(username), now_timestamp()),
        )


class SessionRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    def create(self, username: str, expires_at: str, client_id: str = "", device_info: str = "") -> dict:
        session_id = str(uuid4())
        created_at = now_timestamp()
        self.database.execute(
            """
            INSERT INTO sessions(
                session_id, username, created_at, expires_at, active, client_id, device_info
            ) VALUES(?, ?, ?, ?, 1, ?, ?)
            """,
            (session_id, only_upper(username), created_at, expires_at, client_id, device_info),
        )
        return self.get(session_id) or {
            "session_id": session_id,
            "username": only_upper(username),
            "created_at": created_at,
            "expires_at": expires_at,
            "active": True,
            "client_id": client_id,
            "device_info": device_info,
        }

    def get(self, session_id: str) -> dict | None:
        row = self.database.fetchone(
            """
            SELECT session_id, username, created_at, expires_at, active, client_id, device_info
            FROM sessions
            WHERE session_id = ?
            """,
            (session_id,),
        )
        if not row:
            return None
        row["active"] = parse_bool(row["active"])
        return row

    def is_active(self, session_id: str) -> bool:
        session = self.get(session_id)
        if not session or not session["active"]:
            return False
        expires_at = datetime.fromisoformat(session["expires_at"])
        if expires_at <= datetime.now():
            self.deactivate(session_id)
            return False
        return True

    def deactivate(self, session_id: str) -> None:
        self.database.execute(
            "UPDATE sessions SET active = 0 WHERE session_id = ?",
            (session_id,),
        )

    def deactivate_for_user(self, username: str) -> None:
        self.database.execute(
            "UPDATE sessions SET active = 0 WHERE username = ?",
            (only_upper(username),),
        )

    def purge_expired(self) -> None:
        self.database.execute(
            "UPDATE sessions SET active = 0 WHERE active = 1 AND expires_at <= ?",
            (now_timestamp(),),
        )

    def list_all(self) -> list[dict]:
        return self.database.fetchall(
            """
            SELECT session_id, username, created_at, expires_at, active, client_id, device_info
            FROM sessions
            ORDER BY created_at DESC
            """
        )
