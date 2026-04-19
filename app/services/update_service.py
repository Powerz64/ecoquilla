from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import (
    APP_NAME,
    APP_VERSION,
    UPDATE_METADATA_URL,
    UPDATE_SIGNER_SUBJECT,
    UPDATE_SIGNER_THUMBPRINT,
)


NETWORK_TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_ATTEMPTS = 2
CHUNK_SIZE = 1024 * 128


@dataclass
class UpdateCheckResult:
    ok: bool
    message: str
    update_available: bool = False
    latest_version: str = ""
    download_url: str = ""
    notes: str = ""
    sha256: str = ""


@dataclass
class UpdateDownloadResult:
    ok: bool
    message: str
    file_path: str = ""
    sha256: str = ""


@dataclass
class UpdateInstallResult:
    ok: bool
    message: str
    process_id: int | None = None


class UpdateService:
    """Check, download, validate, and launch desktop application updates."""

    def __init__(
        self,
        *,
        metadata_url: str = UPDATE_METADATA_URL,
        current_version: str = APP_VERSION,
        trusted_signer_subject: str = UPDATE_SIGNER_SUBJECT,
        trusted_signer_thumbprint: str = UPDATE_SIGNER_THUMBPRINT,
        log_service=None,
    ):
        self.metadata_url = str(metadata_url or "").strip()
        self.current_version = str(current_version or "").strip()
        self.trusted_signer_subject = str(trusted_signer_subject or "").strip()
        self.trusted_signer_thumbprint = self._normalize_thumbprint(trusted_signer_thumbprint)
        self.log_service = log_service
        self.download_dir = Path(tempfile.gettempdir()) / "ECOQUILLA"

    def is_configured(self) -> bool:
        return bool(self.metadata_url)

    def check_for_updates(
        self,
        *,
        actor: str = "SISTEMA",
        session_id: str = "",
    ) -> UpdateCheckResult:
        if not self.metadata_url:
            return UpdateCheckResult(False, "No se ha configurado un origen de actualizaciones.")

        self._log("info", actor, "UPDATE_CHECK", f"Consultando {self.metadata_url}", session_id=session_id)

        payload, error_message = self._fetch_json(self.metadata_url)
        if payload is None:
            self._log("error", actor, "UPDATE_CHECK", error_message, session_id=session_id)
            return UpdateCheckResult(False, error_message)

        latest_version = str(payload.get("version", "")).strip()
        download_url = str(payload.get("url", "")).strip()
        notes = self._normalize_notes(payload.get("notes", ""))
        sha256_value = str(payload.get("sha256", "")).strip().lower()

        if not latest_version or not download_url:
            message = "El servidor no devolvió una actualización válida."
            self._log("error", actor, "UPDATE_CHECK", message, session_id=session_id)
            return UpdateCheckResult(False, message)

        update_available = self._compare_versions(latest_version, self.current_version) > 0
        if update_available:
            self._log(
                "info",
                actor,
                "UPDATE_AVAILABLE",
                f"Versión {latest_version} disponible.",
                session_id=session_id,
            )
            message = f"Nueva versión disponible: {latest_version}"
        else:
            message = f"La aplicación ya está actualizada (v{self.current_version})."
            self._log("info", actor, "UPDATE_CHECK", message, session_id=session_id)

        return UpdateCheckResult(
            True,
            message,
            update_available=update_available,
            latest_version=latest_version,
            download_url=download_url,
            notes=notes,
            sha256=sha256_value,
        )

    def get_latest_release_url(self) -> str:
        """Return the direct installer URL from update metadata for future GitHub Release integrations."""
        payload, _error_message = self._fetch_json(self.metadata_url)
        if payload is None:
            return ""
        return str(payload.get("url", "")).strip()

    def download_update(
        self,
        url: str,
        *,
        latest_version: str,
        expected_sha256: str = "",
        actor: str = "SISTEMA",
        session_id: str = "",
        progress_callback=None,
    ) -> UpdateDownloadResult:
        download_url = str(url or "").strip()
        version_label = str(latest_version or "").strip()
        expected_sha256 = str(expected_sha256 or "").strip().lower()
        if not download_url:
            return UpdateDownloadResult(False, "La actualización no tiene una URL de descarga válida.")
        if not version_label:
            return UpdateDownloadResult(False, "La actualización no especifica una versión válida.")

        self.download_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.download_dir / self._build_installer_filename(version_label)
        self._cleanup_old_downloads(keep={target_path.name})
        if progress_callback is not None:
            progress_callback(0)

        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                if target_path.exists():
                    target_path.unlink()

                request = Request(
                    download_url,
                    headers={"User-Agent": f"{APP_NAME}/{self.current_version}"},
                )
                with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response, target_path.open("wb") as output_file:
                    total_bytes = self._read_content_length(response)
                    received_bytes = 0
                    last_reported_percent = -1

                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        output_file.write(chunk)
                        received_bytes += len(chunk)
                        if total_bytes > 0 and progress_callback is not None:
                            percent = min(int((received_bytes * 100) / total_bytes), 100)
                            if percent != last_reported_percent:
                                progress_callback(percent)
                                last_reported_percent = percent

                if progress_callback is not None:
                    progress_callback(100)

                if not target_path.exists() or target_path.stat().st_size <= 0:
                    raise OSError("El instalador descargado está vacío.")

                actual_sha256 = self._compute_sha256(target_path)
                if expected_sha256 and actual_sha256 != expected_sha256:
                    if target_path.exists():
                        target_path.unlink()
                    message = "La actualización descargada no superó la validación de integridad."
                    self._log("error", actor, "UPDATE_DOWNLOAD_FAIL", message, session_id=session_id)
                    return UpdateDownloadResult(False, message)

                signature_valid, signature_status = self.verify_signature(target_path)
                if not signature_valid:
                    if target_path.exists():
                        target_path.unlink()
                    self._log(
                        "error",
                        actor,
                        "UPDATE_SIGNATURE_INVALID",
                        f"{target_path.name}: {signature_status}",
                        session_id=session_id,
                    )
                    return UpdateDownloadResult(False, "El instalador no es confiable")

                self._log(
                    "info",
                    actor,
                    "UPDATE_DOWNLOAD_SUCCESS",
                    f"{target_path} ({actual_sha256})",
                    session_id=session_id,
                )
                return UpdateDownloadResult(
                    True,
                    "Actualización descargada correctamente.",
                    file_path=str(target_path),
                    sha256=actual_sha256,
                )
            except (HTTPError, URLError, TimeoutError, OSError) as error:
                if target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                    message = self._build_download_error_message(error)
                    self._log("error", actor, "UPDATE_DOWNLOAD_FAIL", message, session_id=session_id)
                    return UpdateDownloadResult(False, message)
            except Exception:
                if target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                message = "No se pudo descargar el instalador de actualización."
                self._log("error", actor, "UPDATE_DOWNLOAD_FAIL", message, session_id=session_id)
                return UpdateDownloadResult(False, message)

        message = "No se pudo descargar el instalador de actualización."
        self._log("error", actor, "UPDATE_DOWNLOAD_FAIL", message, session_id=session_id)
        return UpdateDownloadResult(False, message)

    def install_update(
        self,
        file_path: str | Path,
        *,
        actor: str = "SISTEMA",
        session_id: str = "",
    ) -> UpdateInstallResult:
        installer_path = Path(file_path).expanduser().resolve()
        if not installer_path.exists():
            return UpdateInstallResult(False, "No se encontró el instalador descargado.")

        signature_valid, signature_status = self.verify_signature(installer_path)
        if not signature_valid:
            self._log(
                "error",
                actor,
                "UPDATE_SIGNATURE_INVALID",
                f"{installer_path.name}: {signature_status}",
                session_id=session_id,
            )
            return UpdateInstallResult(False, "El instalador no es confiable")

        try:
            process = subprocess.Popen([str(installer_path)])
            if process.pid is None:
                raise OSError("El instalador no devolvió un proceso válido.")
            time.sleep(0.5)
            if process.poll() is not None:
                raise OSError("El instalador se cerró antes de iniciar correctamente.")
        except Exception:
            message = "No se pudo iniciar el instalador de actualización."
            self._log("error", actor, "UPDATE_DOWNLOAD_FAIL", message, session_id=session_id)
            return UpdateInstallResult(False, message)

        self._log(
            "info",
            actor,
            "UPDATE_INSTALL_LAUNCHED",
            f"{installer_path} (PID {process.pid})",
            session_id=session_id,
        )
        self._schedule_installer_cleanup(installer_path, actor=actor, session_id=session_id)
        return UpdateInstallResult(True, "Instalador iniciado correctamente.", process_id=process.pid)

    def verify_signature(self, file_path: str | Path) -> tuple[bool, str]:
        installer_path = Path(file_path).expanduser().resolve()
        if not installer_path.exists():
            return False, "FILE_NOT_FOUND"

        signature_info, error_detail = self._get_signature_info_powershell(installer_path)
        if signature_info is not None:
            status = str(signature_info.get("Status", "")).strip() or "UNKNOWN"
            subject = str(signature_info.get("Subject", "")).strip()
            thumbprint = self._normalize_thumbprint(signature_info.get("Thumbprint", ""))

            if status.upper() != "VALID":
                return False, status
            if not self._is_trusted_signer(subject, thumbprint):
                detail = (
                    "UNTRUSTED_SIGNER "
                    f"subject={subject or 'UNKNOWN'} "
                    f"thumbprint={thumbprint or 'UNKNOWN'}"
                )
                return False, detail
            return True, f"VALID ({thumbprint or subject or 'UNKNOWN'})"

        signtool_ok, signtool_detail = self._verify_signature_signtool(installer_path)
        if not signtool_ok:
            return False, signtool_detail or error_detail or "UNKNOWN"

        certificate_info, certificate_error = self._get_signer_identity(installer_path)
        if certificate_info is None:
            return False, certificate_error or "UNKNOWN_SIGNER"

        subject = str(certificate_info.get("Subject", "")).strip()
        thumbprint = self._normalize_thumbprint(certificate_info.get("Thumbprint", ""))
        if not self._is_trusted_signer(subject, thumbprint):
            detail = (
                "UNTRUSTED_SIGNER "
                f"subject={subject or 'UNKNOWN'} "
                f"thumbprint={thumbprint or 'UNKNOWN'}"
            )
            return False, detail
        return True, f"VALID ({thumbprint or subject or 'UNKNOWN'})"

    def _get_signature_info_powershell(self, installer_path: Path) -> tuple[dict | None, str]:
        escaped_path = str(installer_path).replace("'", "''")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$ErrorActionPreference = 'Stop'; "
                f"$sig = Get-AuthenticodeSignature -FilePath '{escaped_path}'; "
                "$cert = $sig.SignerCertificate; "
                "[pscustomobject]@{"
                "Status = [string]$sig.Status; "
                "Subject = if ($null -ne $cert) { [string]$cert.Subject } else { '' }; "
                "Thumbprint = if ($null -ne $cert) { [string]$cert.Thumbprint } else { '' }"
                "} | ConvertTo-Json -Compress"
            ),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            return None, "POWERSHELL_UNAVAILABLE"

        output = (result.stdout or "").strip()
        if result.returncode != 0 or not output:
            return None, ((result.stderr or "").strip() or "POWERSHELL_SIGNATURE_FAILED")
        try:
            return json.loads(output), ""
        except json.JSONDecodeError:
            return None, "POWERSHELL_SIGNATURE_INVALID_OUTPUT"

    def _get_signer_identity(self, installer_path: Path) -> tuple[dict | None, str]:
        escaped_path = str(installer_path).replace("'", "''")
        command = [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "$ErrorActionPreference = 'Stop'; "
                f"$sig = Get-AuthenticodeSignature -FilePath '{escaped_path}'; "
                "$cert = $sig.SignerCertificate; "
                "if ($null -eq $cert) { throw 'NO_CERTIFICATE' }; "
                "[pscustomobject]@{"
                "Subject = [string]$cert.Subject; "
                "Thumbprint = [string]$cert.Thumbprint"
                "} | ConvertTo-Json -Compress"
            ),
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            return None, "SIGNER_IDENTITY_UNAVAILABLE"

        output = (result.stdout or "").strip()
        if result.returncode != 0 or not output:
            return None, ((result.stderr or "").strip() or "SIGNER_IDENTITY_UNAVAILABLE")
        try:
            return json.loads(output), ""
        except json.JSONDecodeError:
            return None, "SIGNER_IDENTITY_INVALID_OUTPUT"

    def _verify_signature_signtool(self, installer_path: Path) -> tuple[bool, str]:
        signtool_path = shutil.which("signtool.exe") or shutil.which("signtool")
        if not signtool_path:
            return False, "SIGNTOOL_UNAVAILABLE"

        command = [signtool_path, "verify", "/pa", str(installer_path)]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except Exception:
            return False, "SIGNTOOL_VERIFY_FAILED"

        if result.returncode == 0:
            return True, "VALID"

        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        return False, output or "SIGNTOOL_VERIFY_FAILED"

    def _fetch_json(self, url: str) -> tuple[dict | None, str]:
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                request = Request(
                    url,
                    headers={
                        "User-Agent": f"{APP_NAME}/{self.current_version}",
                        "Accept": "application/json",
                    },
                )
                with urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    return None, "La respuesta del servidor de actualizaciones no es válida."
                return payload, ""
            except HTTPError as error:
                if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                    return None, f"No se pudo consultar el servidor de actualizaciones ({error.code})."
            except URLError:
                if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                    return None, "No fue posible conectarse al servidor de actualizaciones."
            except json.JSONDecodeError:
                return None, "La respuesta del servidor de actualizaciones no es válida."
            except Exception:
                if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                    return None, "Ocurrió un error inesperado al buscar actualizaciones."
        return None, "Ocurrió un error inesperado al buscar actualizaciones."

    def _read_content_length(self, response) -> int:
        content_length = response.headers.get("Content-Length", "").strip()
        try:
            return max(int(content_length), 0)
        except (TypeError, ValueError):
            return 0

    def _build_installer_filename(self, version: str) -> str:
        safe_version = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in version)
        safe_version = safe_version.strip("._") or "latest"
        return f"ecoquilla_update_{safe_version}.exe"

    def _cleanup_old_downloads(self, *, keep: set[str] | None = None) -> None:
        keep = keep or set()
        if not self.download_dir.exists():
            return
        for candidate in self.download_dir.glob("ecoquilla_update_*.exe"):
            if candidate.name in keep:
                continue
            try:
                candidate.unlink()
            except OSError:
                continue

    def _schedule_installer_cleanup(self, installer_path: Path, *, actor: str, session_id: str) -> None:
        cleanup_script = Path(tempfile.gettempdir()) / "ecoquilla_cleanup.bat"
        installer_literal = str(installer_path).replace('"', '""')
        cleanup_glob = str((self.download_dir / "ecoquilla_update_*.exe").resolve()).replace('"', '""')
        script_lines = [
            "@echo off",
            "timeout /t 5 /nobreak >nul",
            f'del /f /q "{installer_literal}" >nul 2>&1',
            f'del /f /q "{cleanup_glob}" >nul 2>&1',
            'del "%~f0"',
            "",
        ]
        try:
            cleanup_script.write_text("\r\n".join(script_lines), encoding="ascii")
            subprocess.Popen(f'"{cleanup_script}"', shell=True)
            self._log(
                "info",
                actor,
                "UPDATE_DOWNLOAD_CLEANUP",
                f"Limpieza diferida programada para: {installer_path.name}",
                session_id=session_id,
            )
        except OSError:
            self._log(
                "warning",
                actor,
                "UPDATE_DOWNLOAD_CLEANUP",
                f"No se pudo programar la limpieza del instalador temporal: {installer_path.name}",
                session_id=session_id,
            )
        except Exception:
            self._log(
                "warning",
                actor,
                "UPDATE_DOWNLOAD_CLEANUP",
                f"No se pudo lanzar el script de limpieza diferida: {installer_path.name}",
                session_id=session_id,
            )

    def _compute_sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _build_download_error_message(self, error: Exception) -> str:
        if isinstance(error, HTTPError):
            return f"No se pudo descargar la actualización ({error.code})."
        if isinstance(error, URLError):
            return "Falló la descarga de la actualización por un problema de red."
        if isinstance(error, TimeoutError):
            return "La descarga de la actualización tardó demasiado y fue cancelada."
        if isinstance(error, OSError):
            return str(error) or "No se pudo descargar el instalador de actualización."
        return "No se pudo descargar el instalador de actualización."

    def _normalize_notes(self, raw_notes) -> str:
        if isinstance(raw_notes, list):
            return "\n".join(f"- {str(item).strip()}" for item in raw_notes if str(item).strip())
        if isinstance(raw_notes, dict):
            lines = []
            for key, value in raw_notes.items():
                clean_key = str(key).strip()
                clean_value = str(value).strip()
                if clean_key and clean_value:
                    lines.append(f"- {clean_key}: {clean_value}")
            return "\n".join(lines)
        return str(raw_notes or "").strip()

    def _compare_versions(self, latest_version: str, current_version: str) -> int:
        left = self._version_tuple(latest_version)
        right = self._version_tuple(current_version)
        max_size = max(len(left), len(right))
        left += (0,) * (max_size - len(left))
        right += (0,) * (max_size - len(right))
        if left > right:
            return 1
        if left < right:
            return -1
        return 0

    def _version_tuple(self, version: str) -> tuple[int, ...]:
        parts = []
        for chunk in str(version).replace("-", ".").split("."):
            digits = "".join(char for char in chunk if char.isdigit())
            parts.append(int(digits or 0))
        return tuple(parts or [0])

    def _normalize_thumbprint(self, value) -> str:
        return str(value or "").strip().replace(" ", "").upper()

    def _is_trusted_signer(self, subject: str, thumbprint: str) -> bool:
        normalized_subject = str(subject or "").upper()
        normalized_thumbprint = self._normalize_thumbprint(thumbprint)
        thumbprint_match = (
            bool(self.trusted_signer_thumbprint)
            and normalized_thumbprint == self.trusted_signer_thumbprint
        )
        subject_match = (
            bool(self.trusted_signer_subject)
            and self.trusted_signer_subject.upper() in normalized_subject
        )
        return thumbprint_match or subject_match

    def _log(self, level: str, actor: str, action: str, detail: str, *, session_id: str = "") -> None:
        if self.log_service is None:
            return
        logger = getattr(self.log_service, level.lower(), None)
        if logger is None:
            return
        logger(actor or "SISTEMA", action, detail, session_id=session_id)
