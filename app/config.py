from __future__ import annotations

import json
import os
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
IS_FROZEN = bool(getattr(sys, "frozen", False))
PROJECT_ROOT = Path(sys.executable).resolve().parent if IS_FROZEN else SOURCE_ROOT
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
APP_DATA_DIR = (
    (Path(os.getenv("LOCALAPPDATA", "")) / "ECOQUILLA").resolve()
    if IS_FROZEN and os.getenv("LOCALAPPDATA")
    else PROJECT_ROOT
)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = APP_DATA_DIR / "settings.json"
ENV_FILE = APP_DATA_DIR / ".env"
ICON_FILE = RESOURCE_ROOT / "ecoquilla.ico"

APP_NAME = "ECOQUILLA SAS PRO MAX ENTERPRISES"
APP_COMPANY = "ECOQUILLA SAS"
APP_COPYRIGHT = "© 2026 Miguel Cuello"
UNINSTALL_PIN = "2914"

DEFAULT_SETTINGS = {
    "app_name": APP_NAME,
    "app_version": "1.0.0",
    "company_name": APP_COMPANY,
    "city": "Barranquilla",
    "country": "CO",
    "security": {
        "max_login_attempts": 3,
        "login_block_seconds": 30,
        "session_timeout_minutes": 120,
        "security_level": "HIGH",
    },
    "analytics": {
        "high_error_rate_threshold": 0.25,
        "inactive_zone_days": 7,
        "heavy_contributor_kg_threshold": 100.0,
        "max_weight_kg": 5000.0,
    },
    "files": {
        "data_dir": "runtime_data",
        "backup_dir": "backups",
        "export_dir": "exports",
        "db_name": "ecoquilla.db",
    },
    "updates": {
        "metadata_url": "",
        "check_on_start": True,
        "skip_version": "",
        "signer_subject": APP_COMPANY,
        "signer_thumbprint": "",
    },
}


def _deep_merge(base: dict, incoming: dict) -> dict:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.exists():
        return values

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().upper()] = value.strip().strip('"').strip("'")
    return values


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        SETTINGS_FILE.write_text(
            json.dumps(DEFAULT_SETTINGS, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return DEFAULT_SETTINGS

    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw = {}

    merged = _deep_merge(DEFAULT_SETTINGS, raw)
    merged["app_name"] = APP_NAME
    merged["company_name"] = APP_COMPANY
    SETTINGS_FILE.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return merged


def save_settings() -> None:
    SETTINGS_FILE.write_text(
        json.dumps(SETTINGS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = APP_DATA_DIR / path
    return path


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "si", "on"}


SETTINGS = load_settings()
ENV = _load_env()

APP_VERSION = SETTINGS["app_version"]
COMPANY_NAME = SETTINGS["company_name"]
APP_LOCATION = f"{SETTINGS['city']} · {SETTINGS['country']}"

DATA_DIR = _resolve_path(SETTINGS["files"]["data_dir"])
BACKUP_DIR = _resolve_path(SETTINGS["files"]["backup_dir"])
EXPORT_DIR = _resolve_path(SETTINGS["files"]["export_dir"])

USERS_FILE = DATA_DIR / "usuarios.json"
RECORDS_FILE = DATA_DIR / "registros.json"
LOGS_FILE = DATA_DIR / "logs.json"
ATTEMPTS_FILE = DATA_DIR / "login_attempts.json"

DB_PATH = _resolve_path(ENV.get("DB_PATH") or (DATA_DIR / SETTINGS["files"]["db_name"]))
MAX_LOGIN_ATTEMPTS = int(SETTINGS["security"]["max_login_attempts"])
LOGIN_BLOCK_SECONDS = int(SETTINGS["security"]["login_block_seconds"])
SESSION_TIMEOUT_MINUTES = int(
    ENV.get("SESSION_TIMEOUT") or SETTINGS["security"]["session_timeout_minutes"]
)
SECURITY_LEVEL = ENV.get("SECURITY_LEVEL", SETTINGS["security"]["security_level"]).upper()
UPDATE_METADATA_URL = (
    ENV.get("UPDATE_METADATA_URL")
    or SETTINGS["updates"]["metadata_url"]
).strip()
UPDATE_CHECK_ON_START = _to_bool(
    ENV.get("UPDATE_CHECK_ON_START", SETTINGS["updates"]["check_on_start"])
)
UPDATE_SIGNER_SUBJECT = str(
    ENV.get("UPDATE_SIGNER_SUBJECT")
    or SETTINGS["updates"].get("signer_subject")
    or APP_COMPANY
).strip()
UPDATE_SIGNER_THUMBPRINT = str(
    ENV.get("UPDATE_SIGNER_THUMBPRINT")
    or SETTINGS["updates"].get("signer_thumbprint", "")
).strip().replace(" ", "").upper()

HIGH_ERROR_RATE_THRESHOLD = float(SETTINGS["analytics"]["high_error_rate_threshold"])
INACTIVE_ZONE_DAYS = int(SETTINGS["analytics"]["inactive_zone_days"])
HEAVY_CONTRIBUTOR_KG_THRESHOLD = float(SETTINGS["analytics"]["heavy_contributor_kg_threshold"])
MAX_WEIGHT_KG = float(SETTINGS["analytics"]["max_weight_kg"])

for runtime_dir in (DATA_DIR, BACKUP_DIR, EXPORT_DIR):
    runtime_dir.mkdir(parents=True, exist_ok=True)


COLORS = {
    "bg_dark": "#0e1624",
    "bg_panel": "#152235",
    "bg_card": "#1a2940",
    "bg_row": "#22344e",
    "bg_soft": "#2a4162",
    "accent": "#00e5a0",
    "accent_dim": "#08c88e",
    "accent_blue": "#3b9eff",
    "accent_yellow": "#f5c842",
    "accent_red": "#ff4d6a",
    "accent_purple": "#a855f7",
    "accent_orange": "#fb923c",
    "text_primary": "#e8f0fe",
    "text_secondary": "#a7bad7",
    "border": "#345071",
    "hover": "#35577f",
    "selected": "#3f73b8",
    "shadow": "#08111b",
    "success": "#10b981",
    "danger": "#ef4444",
    "warning": "#f59e0b",
}

MATERIAL_COLORS = {
    "PLASTICO": "#3b9eff",
    "PAPEL": "#f5c842",
    "VIDRIO": "#00e5a0",
    "METAL": "#a855f7",
    "ORGANICO": "#fb923c",
    "CARTON": "#f97316",
}

FONT_TITLE = ("Consolas", 18, "bold")
FONT_SUB = ("Consolas", 10)
FONT_BUTTON = ("Consolas", 10, "bold")
FONT_TEXT = ("Consolas", 9)
FONT_MINI = ("Consolas", 8)
FONT_KPI = ("Consolas", 22, "bold")

VALID_COLLECTION_DAYS = ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES"]
ALL_COLLECTION_DAYS = VALID_COLLECTION_DAYS + ["SABADO", "DOMINGO"]
VALID_RESIDUES = ["PLASTICO", "PAPEL", "VIDRIO", "METAL", "ORGANICO", "CARTON"]
VALID_ZONES = ["NORTE", "SUR", "CENTRO", "ORIENTE", "OCCIDENTE", "SUROCCIDENTE"]
VALID_ROLES = ["ADMIN", "OPERADOR", "LECTURA"]


def apply_plot_theme(plt_module) -> None:
    plt_module.rcParams.update(
        {
            "axes.edgecolor": COLORS["border"],
            "axes.labelcolor": COLORS["text_secondary"],
            "xtick.color": COLORS["text_secondary"],
            "ytick.color": COLORS["text_secondary"],
            "text.color": COLORS["text_primary"],
        }
    )


def get_skipped_update_version() -> str:
    return str(SETTINGS.get("updates", {}).get("skip_version", "")).strip()


def set_skipped_update_version(version: str) -> None:
    SETTINGS.setdefault("updates", {})["skip_version"] = str(version or "").strip()
    save_settings()


def clear_skipped_update_version() -> None:
    set_skipped_update_version("")
