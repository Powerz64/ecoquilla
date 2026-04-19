from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.config import SESSION_TIMEOUT_MINUTES
from app.core.security import hash_password, password_needs_upgrade, verify_password
from app.core.utils import now_date, now_time, only_upper


@dataclass
class AuthResult:
    ok: bool
    message: str
    username: str = ""
    role: str = ""
    blocked_seconds: int = 0
    session_id: str = ""
    expires_at: str = ""


class AuthService:
    """Handle authentication, login protection, and session lifecycle."""

    def __init__(
        self,
        user_repository,
        attempt_repository,
        session_repository,
        log_service,
    ):
        self.user_repository = user_repository
        self.attempt_repository = attempt_repository
        self.session_repository = session_repository
        self.log_service = log_service

    def authenticate(
        self,
        username: str,
        password: str,
        *,
        client_id: str = "desktop-local",
        device_info: str = "tkinter-desktop",
    ) -> AuthResult:
        username = only_upper(username)
        password = password.strip()
        self.session_repository.purge_expired()

        if not username or not password:
            return AuthResult(False, "Ingrese usuario y contrasena.")

        blocked_seconds = self.attempt_repository.blocked_seconds(username)
        if blocked_seconds:
            return AuthResult(
                False,
                f"Demasiados intentos. Espere {blocked_seconds} segundo(s).",
                blocked_seconds=blocked_seconds,
            )

        user = self.user_repository.get(username)
        if not user:
            attempt_info = self.attempt_repository.register_failure(
                username,
                client_id=client_id,
                device_info=device_info,
            )
            self.log_service.warning(username, "LOGIN FALLIDO", "USUARIO NO EXISTE")
            if attempt_info["blocked"]:
                return AuthResult(
                    False,
                    "Maximo de intentos alcanzado.",
                    blocked_seconds=attempt_info["blocked_seconds"],
                )
            return AuthResult(
                False,
                f"Usuario no existe. Intentos restantes: {attempt_info['remaining_attempts']}",
            )

        if not user.get("activo", True):
            self.log_service.warning(username, "LOGIN BLOQUEADO", "USUARIO INACTIVO")
            return AuthResult(False, "El usuario esta desactivado.")

        if not verify_password(password, user.get("password", "")):
            attempt_info = self.attempt_repository.register_failure(
                username,
                client_id=client_id,
                device_info=device_info,
            )
            self.log_service.warning(username, "LOGIN FALLIDO", "CONTRASENA INCORRECTA")
            if attempt_info["blocked"]:
                return AuthResult(
                    False,
                    "Maximo de intentos alcanzado.",
                    blocked_seconds=attempt_info["blocked_seconds"],
                )
            return AuthResult(
                False,
                f"Contrasena incorrecta. Intentos restantes: {attempt_info['remaining_attempts']}",
            )

        if password_needs_upgrade(user.get("password", "")):
            user["password"] = hash_password(password)

        user["ultimo_acceso"] = f"{now_date()} {now_time()}"
        self.user_repository.upsert(username, user)
        self.attempt_repository.reset(username)
        self.session_repository.deactivate_for_user(username)
        expires_at = (datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)).isoformat(timespec="seconds")
        session = self.session_repository.create(
            username,
            expires_at,
            client_id=client_id,
            device_info=device_info,
        )
        self.log_service.info(
            username,
            "LOGIN EXITOSO",
            "ACCESO CONCEDIDO",
            session_id=session["session_id"],
        )
        return AuthResult(
            True,
            "Acceso concedido.",
            username=username,
            role=user.get("rol", "OPERADOR"),
            session_id=session["session_id"],
            expires_at=session["expires_at"],
        )

    def is_session_active(self, session_id: str) -> bool:
        if not session_id:
            return False
        return self.session_repository.is_active(session_id)

    def get_session(self, session_id: str) -> dict | None:
        return self.session_repository.get(session_id)

    def close_session(self, session_id: str, username: str) -> None:
        if session_id:
            self.session_repository.deactivate(session_id)
        self.log_service.info(username, "CERRAR SESION", "SALIDA MANUAL DEL SISTEMA", session_id=session_id)

    def register_exit(self, session_id: str, username: str) -> None:
        if session_id:
            self.session_repository.deactivate(session_id)
        self.log_service.info(username, "SALIR APP", "CIERRE DE VENTANA PRINCIPAL", session_id=session_id)
