from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from app.config import BACKUP_DIR, PROJECT_ROOT
from app.core.exceptions import DataStoreError


class SystemService:
    """Operational helpers that sit above repositories without touching Tkinter."""

    def __init__(
        self,
        record_repository,
        user_repository,
        session_repository,
        log_service,
    ):
        self.record_repository = record_repository
        self.user_repository = user_repository
        self.session_repository = session_repository
        self.log_service = log_service

    def list_logs(self, filter_text: str = "") -> list[dict]:
        return self.log_service.list_logs(filter_text)

    def create_backup(self, actor: str, *, session_id: str = "") -> Path:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = BACKUP_DIR / f"backup_{timestamp}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        (backup_dir / "registros.json").write_text(
            json.dumps(self.record_repository.list_all(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (backup_dir / "usuarios.json").write_text(
            json.dumps(self.user_repository.list_all(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (backup_dir / "logs.json").write_text(
            json.dumps(self.log_service.list_logs(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (backup_dir / "sessions.json").write_text(
            json.dumps(self.session_repository.list_all(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self.log_service.info(actor, "BACKUP", f"BACKUP GENERADO {backup_dir.name}", session_id=session_id)
        return backup_dir

    def get_uninstaller_path(self) -> Path:
        current_install_uninstaller = self._current_install_uninstaller_path()
        if current_install_uninstaller.exists() and current_install_uninstaller.is_file():
            return current_install_uninstaller

        for path in self._fallback_uninstaller_paths():
            if path.exists() and path.is_file():
                return path

        raise DataStoreError(
            "No se encontro el desinstalador. Verifica que ECOQUILLA este instalada correctamente."
        )

    def uninstall_application(self, actor: str, *, session_id: str = "") -> Path:
        uninstaller_path = self.get_uninstaller_path()
        self.log_service.warning(
            actor,
            "SYSTEM UNINSTALL START",
            f"DESINSTALADOR DEL SISTEMA INICIADO: {uninstaller_path}",
            session_id=session_id,
        )
        try:
            process = self._launch_uninstaller(uninstaller_path)
        except DataStoreError as error:
            self.log_service.error(
                actor,
                "SYSTEM UNINSTALL FAILURE",
                f"NO SE PUDO INICIAR EL DESINSTALADOR: {error}",
                session_id=session_id,
            )
            raise

        self.log_service.info(
            actor,
            "SYSTEM UNINSTALL LAUNCHED",
            f"DESINSTALADOR INICIADO CON PID {process.pid}: {uninstaller_path}",
            session_id=session_id,
        )
        return uninstaller_path

    @staticmethod
    def _current_install_uninstaller_path() -> Path:
        return (Path(sys.executable).resolve().parent / "unins000.exe").resolve()

    @staticmethod
    def _fallback_uninstaller_paths() -> list[Path]:
        candidates: list[Path] = []
        seen: set[Path] = set()

        def add_candidate(path: Path) -> None:
            resolved = path.expanduser().resolve()
            if resolved not in seen:
                candidates.append(resolved)
                seen.add(resolved)

        install_dir = PROJECT_ROOT.resolve()
        add_candidate(install_dir / "unins000.exe")

        for env_var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base_dir = os.environ.get(env_var, "").strip()
            if base_dir:
                add_candidate(Path(base_dir) / "ECOQUILLA" / "unins000.exe")

        return candidates

    @staticmethod
    def _launch_uninstaller(uninstaller_path: Path) -> subprocess.Popen:
        try:
            process = subprocess.Popen(
                [str(uninstaller_path)],
                cwd=str(uninstaller_path.parent),
            )
            if process.pid is None:
                raise DataStoreError("El desinstalador no devolvio un identificador de proceso valido.")
            time.sleep(0.25)
            if process.poll() is not None:
                raise DataStoreError("No se pudo iniciar el desinstalador correctamente")
            return process
        except PermissionError as exc:
            raise DataStoreError("Ejecuta la aplicación como administrador para desinstalar") from exc
        except OSError as exc:
            if getattr(exc, "winerror", None) in {5, 740}:
                raise DataStoreError("Ejecuta la aplicación como administrador para desinstalar") from exc
            raise DataStoreError(f"No se pudo iniciar la desinstalacion:\n{exc}") from exc
