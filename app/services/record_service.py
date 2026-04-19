from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import EXPORT_DIR
from app.core.utils import only_upper
from app.core.validators import build_record_payload, is_duplicate_record, normalize_record


@dataclass
class ServiceResult:
    ok: bool
    message: str
    errors: list[str] = field(default_factory=list)
    count: int = 0


class RecordService:
    CSV_FIELDS = [
        "id",
        "usuario",
        "registrado",
        "residuo",
        "zona",
        "direccion",
        "dia",
        "peso_kg",
        "cantidad",
        "estado",
        "resultado",
        "fecha",
        "creado_por",
        "notas",
    ]

    def __init__(self, record_repository, log_service):
        self.record_repository = record_repository
        self.log_service = log_service

    def list_records(self) -> list[dict]:
        return [normalize_record(record) for record in self.record_repository.list_all()]

    def create_record(self, payload: dict, actor: str, *, session_id: str = "") -> ServiceResult:
        record, errors = build_record_payload(payload, created_by=actor)
        if errors:
            return ServiceResult(False, "No se pudo guardar el registro.", errors=errors)

        records = self.list_records()
        if is_duplicate_record(record, records):
            return ServiceResult(False, "Registro duplicado detectado.", errors=["Ya existe un registro igual para la misma fecha."])

        self.record_repository.create(record)
        self.log_service.info(actor, "CREAR", f"REGISTRO DE {record['usuario']}", session_id=session_id)
        return ServiceResult(True, "Registro guardado correctamente.")

    def update_record(self, index: int, payload: dict, actor: str, *, session_id: str = "") -> ServiceResult:
        records = self.list_records()
        if index < 0 or index >= len(records):
            return ServiceResult(False, "El registro seleccionado no existe.")

        original = records[index]
        payload["id"] = original.get("id")
        record, errors = build_record_payload(
            payload,
            created_by=original.get("creado_por", actor),
            original_date=original.get("fecha"),
        )
        if errors:
            return ServiceResult(False, "No se pudo actualizar el registro.", errors=errors)

        record["modificado_por"] = only_upper(actor)
        if is_duplicate_record(record, records, exclude_record_id=record["id"]):
            return ServiceResult(False, "Registro duplicado detectado.", errors=["La actualizacion generaria un duplicado."])

        self.record_repository.update(record)
        self.log_service.info(actor, "ACTUALIZAR", f"REGISTRO DE {record['usuario']}", session_id=session_id)
        return ServiceResult(True, "Registro actualizado correctamente.")

    def delete_record(self, index: int, actor: str, *, session_id: str = "") -> ServiceResult:
        records = self.list_records()
        if index < 0 or index >= len(records):
            return ServiceResult(False, "El registro seleccionado no existe.")

        deleted_user = records[index]["usuario"]
        self.record_repository.delete(records[index]["id"])
        self.log_service.warning(actor, "ELIMINAR", f"REGISTRO DE {deleted_user}", session_id=session_id)
        return ServiceResult(True, "Registro eliminado correctamente.")

    def filter_records(
        self,
        query: str = "",
        status: str = "TODOS",
        residue: str = "TODOS",
        zone: str = "TODAS",
    ) -> list[tuple[int, dict]]:
        query = only_upper(query)
        filtered = []
        for index, record in enumerate(self.list_records()):
            search_blob = " ".join(
                [
                    record.get("usuario", ""),
                    record.get("direccion", ""),
                    record.get("zona", ""),
                    record.get("residuo", ""),
                    record.get("dia", ""),
                    record.get("notas", ""),
                    record.get("creado_por", ""),
                ]
            ).upper()

            if query and query not in search_blob:
                continue
            if status != "TODOS" and record.get("estado") != status:
                continue
            if residue != "TODOS" and record.get("residuo") != residue:
                continue
            if zone != "TODAS" and record.get("zona", "CENTRO") != zone:
                continue
            filtered.append((index, record))
        return filtered

    def export_csv(
        self,
        target_path: str | Path,
        records: list[dict] | None,
        actor: str,
        *,
        session_id: str = "",
    ) -> ServiceResult:
        rows = self.list_records() if records is None else records
        if not rows:
            return ServiceResult(False, "No hay registros para exportar.")

        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self.CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        self.log_service.info(actor, "EXPORTAR CSV", str(target), session_id=session_id)
        return ServiceResult(True, f"Archivo generado: {target}", count=len(rows))

    def export_json(
        self,
        target_path: str | Path,
        records: list[dict] | None,
        actor: str,
        *,
        session_id: str = "",
    ) -> ServiceResult:
        rows = self.list_records() if records is None else records
        if not rows:
            return ServiceResult(False, "No hay registros para exportar.")

        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        self.log_service.info(actor, "EXPORTAR JSON", str(target), session_id=session_id)
        return ServiceResult(True, f"Archivo generado: {target}", count=len(rows))

    def import_csv(self, source_path: str | Path, actor: str, *, session_id: str = "") -> ServiceResult:
        source = Path(source_path)
        if not source.exists():
            return ServiceResult(False, "El archivo CSV no existe.")

        imported = 0
        errors = []
        records = self.list_records()
        with source.open("r", newline="", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row_number, row in enumerate(reader, start=2):
                payload = {
                    "usuario": row.get("usuario", ""),
                    "registrado": row.get("registrado", "SI"),
                    "residuo": row.get("residuo", ""),
                    "zona": row.get("zona", "CENTRO"),
                    "direccion": row.get("direccion", ""),
                    "dia": row.get("dia", ""),
                    "peso_kg": row.get("peso_kg") or row.get("cantidad", ""),
                    "notas": row.get("notas", ""),
                    "id": row.get("id", ""),
                    "fecha": row.get("fecha", ""),
                }
                record, row_errors = build_record_payload(
                    payload,
                    created_by=row.get("creado_por", actor) or actor,
                    original_date=row.get("fecha") or None,
                )
                if row_errors:
                    errors.append(f"Fila {row_number}: {' | '.join(row_errors)}")
                    continue
                if is_duplicate_record(record, records):
                    errors.append(f"Fila {row_number}: registro duplicado.")
                    continue

                self.record_repository.create(record)
                records.append(normalize_record(record))
                imported += 1

        self.log_service.info(actor, "IMPORTAR CSV", f"{source.name} | IMPORTADOS: {imported}", session_id=session_id)
        if errors:
            return ServiceResult(
                True,
                f"Importacion terminada con observaciones. Registros importados: {imported}.",
                errors=errors,
                count=imported,
            )
        return ServiceResult(True, f"Importacion exitosa. Registros importados: {imported}.", count=imported)

    def import_json(self, source_path: str | Path, actor: str, *, session_id: str = "") -> ServiceResult:
        source = Path(source_path)
        if not source.exists():
            return ServiceResult(False, "El archivo JSON no existe.")
        try:
            payload_rows = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return ServiceResult(False, "El archivo JSON no es valido.")
        if not isinstance(payload_rows, list):
            return ServiceResult(False, "El JSON debe contener una lista de registros.")

        imported = 0
        errors = []
        records = self.list_records()
        for row_number, row in enumerate(payload_rows, start=1):
            if not isinstance(row, dict):
                errors.append(f"Elemento {row_number}: formato invalido.")
                continue
            record, row_errors = build_record_payload(
                row,
                created_by=row.get("creado_por", actor) or actor,
                original_date=row.get("fecha") or None,
            )
            if row_errors:
                errors.append(f"Elemento {row_number}: {' | '.join(row_errors)}")
                continue
            if is_duplicate_record(record, records):
                errors.append(f"Elemento {row_number}: registro duplicado.")
                continue
            self.record_repository.create(record)
            records.append(normalize_record(record))
            imported += 1

        self.log_service.info(actor, "IMPORTAR JSON", f"{source.name} | IMPORTADOS: {imported}", session_id=session_id)
        if errors:
            return ServiceResult(
                True,
                f"Importacion JSON terminada con observaciones. Registros importados: {imported}.",
                errors=errors,
                count=imported,
            )
        return ServiceResult(True, f"Importacion JSON exitosa. Registros importados: {imported}.", count=imported)

    def default_export_path(self, extension: str = "csv") -> Path:
        filename = "ecoquilla_export.csv" if extension.lower() == "csv" else "ecoquilla_export.json"
        return EXPORT_DIR / filename
