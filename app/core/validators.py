from __future__ import annotations

import re
from uuid import uuid4

from app.config import (
    ALL_COLLECTION_DAYS,
    MAX_WEIGHT_KG,
    VALID_COLLECTION_DAYS,
    VALID_RESIDUES,
    VALID_ZONES,
)
from app.core.utils import format_float, now_date, only_upper, sanitize_text


USERNAME_RE = re.compile(r"^[A-Z0-9_]{3,30}$")


def validate_email(email: str) -> bool:
    email = sanitize_text(email, max_length=120)
    if not email:
        return True
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def validate_username(username: str) -> bool:
    return bool(USERNAME_RE.match(only_upper(username)))


def validate_password(password: str) -> tuple[bool, str]:
    if len(password) < 8:
        return False, "La contrasena debe tener al menos 8 caracteres."
    return True, ""


def validate_positive_weight(raw_weight: str) -> tuple[bool, str]:
    try:
        weight = float(raw_weight)
    except ValueError:
        return False, "El peso debe ser numerico."

    if weight <= 0:
        return False, "El peso debe ser mayor que cero."
    if weight > MAX_WEIGHT_KG:
        return False, f"El peso no puede superar {MAX_WEIGHT_KG:.0f} kg."
    return True, ""


def is_duplicate_record(
    candidate: dict,
    existing_records: list[dict],
    *,
    exclude_record_id: str | None = None,
) -> bool:
    normalized_weight = format_float(candidate.get("peso_kg", candidate.get("cantidad", "0")))
    candidate_key = (
        only_upper(candidate.get("usuario", "")),
        only_upper(candidate.get("residuo", "")),
        only_upper(candidate.get("zona", "")),
        sanitize_text(candidate.get("direccion", ""), uppercase=True),
        only_upper(candidate.get("dia", "")),
        sanitize_text(candidate.get("fecha", "")),
        normalized_weight,
    )

    for existing in existing_records:
        if exclude_record_id and existing.get("id") == exclude_record_id:
            continue
        existing_key = (
            only_upper(existing.get("usuario", "")),
            only_upper(existing.get("residuo", "")),
            only_upper(existing.get("zona", "")),
            sanitize_text(existing.get("direccion", ""), uppercase=True),
            only_upper(existing.get("dia", "")),
            sanitize_text(existing.get("fecha", "")),
            format_float(existing.get("peso_kg", existing.get("cantidad", "0"))),
        )
        if candidate_key == existing_key:
            return True
    return False


def build_record_payload(
    form_data: dict,
    created_by: str,
    original_date: str | None = None,
) -> tuple[dict | None, list[str]]:
    cleaned = {
        "id": sanitize_text(form_data.get("id") or uuid4().hex[:10].upper(), uppercase=True, max_length=20),
        "usuario": sanitize_text(form_data.get("usuario", ""), uppercase=True, max_length=80),
        "registrado": sanitize_text(form_data.get("registrado", ""), uppercase=True, max_length=2),
        "residuo": sanitize_text(form_data.get("residuo", ""), uppercase=True, max_length=30),
        "zona": sanitize_text(form_data.get("zona", ""), uppercase=True, max_length=40),
        "direccion": sanitize_text(form_data.get("direccion", ""), uppercase=True, max_length=160),
        "dia": sanitize_text(form_data.get("dia", ""), uppercase=True, max_length=12),
        "peso_kg": sanitize_text(form_data.get("peso_kg", ""), max_length=24),
        "notas": sanitize_text(form_data.get("notas", ""), max_length=300),
        "creado_por": sanitize_text(created_by, uppercase=True, max_length=40),
        "fecha": sanitize_text(original_date or form_data.get("fecha") or now_date(), max_length=10),
    }

    errors = []
    required_keys = ("usuario", "registrado", "residuo", "zona", "direccion", "dia", "peso_kg")
    for key in required_keys:
        if not cleaned[key]:
            errors.append(f"El campo '{key}' es obligatorio.")

    if cleaned["registrado"] not in {"SI", "NO"}:
        errors.append("El campo 'registrado' debe ser SI o NO.")
    if cleaned["residuo"] and cleaned["residuo"] not in VALID_RESIDUES:
        errors.append("Tipo de residuo no valido.")
    if cleaned["zona"] and cleaned["zona"] not in VALID_ZONES:
        errors.append("Zona no valida.")
    if cleaned["dia"] and cleaned["dia"] not in ALL_COLLECTION_DAYS:
        errors.append("Dia de recoleccion no valido.")
    if cleaned["peso_kg"]:
        is_valid_weight, message = validate_positive_weight(cleaned["peso_kg"])
        if not is_valid_weight:
            errors.append(message)

    if errors:
        return None, errors

    estado = "ERROR"
    if (
        cleaned["registrado"] == "SI"
        and cleaned["residuo"] in VALID_RESIDUES
        and cleaned["dia"] in VALID_COLLECTION_DAYS
    ):
        estado = "VALIDO"

    cleaned["estado"] = estado
    cleaned["resultado"] = estado
    cleaned["peso_kg"] = format_float(cleaned["peso_kg"])
    cleaned["cantidad"] = cleaned["peso_kg"]
    return cleaned, []


def normalize_record(record: dict) -> dict:
    normalized = dict(record)
    normalized.setdefault("id", uuid4().hex[:10].upper())
    normalized.setdefault("zona", "CENTRO")
    normalized.setdefault("peso_kg", record.get("cantidad", "0"))
    normalized.setdefault("cantidad", record.get("peso_kg", "0"))
    normalized.setdefault("notas", "")
    normalized.setdefault("creado_por", "SISTEMA")
    normalized.setdefault("resultado", record.get("estado", "ERROR"))
    normalized.setdefault("fecha", now_date())
    normalized.setdefault("modificado_por", "")

    normalized["usuario"] = sanitize_text(normalized.get("usuario", ""), uppercase=True, max_length=80)
    normalized["registrado"] = sanitize_text(normalized.get("registrado", ""), uppercase=True, max_length=2)
    normalized["residuo"] = sanitize_text(normalized.get("residuo", ""), uppercase=True, max_length=30)
    normalized["zona"] = sanitize_text(normalized.get("zona", "CENTRO"), uppercase=True, max_length=40)
    normalized["direccion"] = sanitize_text(normalized.get("direccion", ""), uppercase=True, max_length=160)
    normalized["dia"] = sanitize_text(normalized.get("dia", ""), uppercase=True, max_length=12)
    normalized["estado"] = sanitize_text(normalized.get("estado", "ERROR"), uppercase=True, max_length=10)
    normalized["resultado"] = sanitize_text(
        normalized.get("resultado", normalized["estado"]),
        uppercase=True,
        max_length=10,
    )
    normalized["peso_kg"] = format_float(normalized.get("peso_kg", "0"))
    normalized["cantidad"] = format_float(normalized.get("cantidad", normalized["peso_kg"]))
    normalized["notas"] = sanitize_text(normalized.get("notas", ""), max_length=300)
    normalized["creado_por"] = sanitize_text(normalized.get("creado_por", "SISTEMA"), uppercase=True, max_length=40)
    normalized["modificado_por"] = sanitize_text(normalized.get("modificado_por", ""), uppercase=True, max_length=40)
    normalized["fecha"] = sanitize_text(normalized.get("fecha", now_date()), max_length=10)
    return normalized
