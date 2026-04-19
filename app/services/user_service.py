from __future__ import annotations

from dataclasses import dataclass, field

from app.config import VALID_ROLES
from app.core.security import hash_password
from app.core.utils import only_upper, sanitize_text
from app.core.validators import validate_email, validate_password, validate_username


@dataclass
class UserResult:
    ok: bool
    message: str
    errors: list[str] = field(default_factory=list)


class UserService:
    """User CRUD and secure registration workflows."""

    def __init__(self, user_repository, log_service):
        self.user_repository = user_repository
        self.log_service = log_service

    def list_users(self) -> dict:
        return self.user_repository.list_all()

    def register_user(
        self,
        payload: dict,
        *,
        actor_username: str = "SISTEMA",
        actor_role: str = "OPERADOR",
        session_id: str = "",
    ) -> UserResult:
        username = only_upper(payload.get("username", ""))
        full_name = sanitize_text(payload.get("nombre_completo", ""), max_length=120)
        email = sanitize_text(payload.get("email", ""), max_length=120)
        password = payload.get("password", "").strip()
        confirm_password = payload.get("confirm_password", "").strip()
        requested_role = only_upper(payload.get("rol", "OPERADOR"))

        errors = []
        if not validate_username(username):
            errors.append("El usuario debe tener entre 3 y 30 caracteres y usar solo letras, numeros o _.")
        if self.user_repository.exists(username):
            errors.append("El nombre de usuario ya existe.")
        if not validate_email(email):
            errors.append("El email no es valido.")
        valid_password, password_message = validate_password(password)
        if not valid_password:
            errors.append(password_message)
        if password != confirm_password:
            errors.append("La confirmacion de contrasena no coincide.")

        role = "OPERADOR"
        if actor_role == "ADMIN" and requested_role in VALID_ROLES:
            role = requested_role
        elif requested_role == "ADMIN" and actor_role != "ADMIN":
            errors.append("Solo un ADMIN puede crear usuarios ADMIN.")

        if errors:
            return UserResult(False, "No se pudo registrar el usuario.", errors=errors)

        user_data = {
            "password": hash_password(password),
            "rol": role,
            "activo": True,
            "nombre_completo": full_name,
            "email": email,
            "ultimo_acceso": "",
        }
        self.user_repository.upsert(username, user_data)
        self.log_service.info(
            actor_username,
            "REGISTRO USUARIO",
            f"USUARIO REGISTRADO: {username}",
            session_id=session_id,
        )
        return UserResult(True, f"Usuario {username} registrado correctamente.")

    def save_user(
        self,
        payload: dict,
        actor: str,
        *,
        actor_role: str = "OPERADOR",
        session_id: str = "",
    ) -> UserResult:
        username = only_upper(payload.get("username", ""))
        full_name = sanitize_text(payload.get("nombre_completo", ""), max_length=120)
        email = sanitize_text(payload.get("email", ""), max_length=120)
        role = only_upper(payload.get("rol", "OPERADOR"))
        is_active = bool(payload.get("activo", True))
        new_password = payload.get("nueva_pass", "").strip()

        errors = []
        if not validate_username(username):
            errors.append("El usuario debe tener entre 3 y 30 caracteres y usar solo letras, numeros o _.")
        if not validate_email(email):
            errors.append("El email no es valido.")
        if role not in VALID_ROLES:
            errors.append("El rol no es valido.")
        if role == "ADMIN" and actor_role != "ADMIN":
            errors.append("Solo un ADMIN puede asignar el rol ADMIN.")

        current = self.user_repository.get(username) or {}
        if new_password:
            is_valid_password, message = validate_password(new_password)
            if not is_valid_password:
                errors.append(message)
        elif not current:
            errors.append("Debe ingresar una contrasena para el nuevo usuario.")

        if errors:
            return UserResult(False, "No se pudo guardar el usuario.", errors=errors)

        user_data = {
            "password": current.get("password", ""),
            "rol": role,
            "activo": is_active,
            "nombre_completo": full_name,
            "email": email,
            "ultimo_acceso": current.get("ultimo_acceso", ""),
        }
        if new_password:
            user_data["password"] = hash_password(new_password)

        self.user_repository.upsert(username, user_data)
        self.log_service.info(
            actor,
            "GESTION USUARIO",
            f"GUARDADO: {username}",
            session_id=session_id,
        )
        return UserResult(True, f"Usuario {username} guardado correctamente.")
