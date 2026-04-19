from __future__ import annotations

import re
from datetime import datetime


def now_date() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def now_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def only_upper(value: object) -> str:
    return sanitize_text(value, uppercase=True)


def sanitize_text(
    value: object,
    *,
    uppercase: bool = False,
    max_length: int | None = None,
) -> str:
    text = str(value or "")
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if uppercase:
        text = text.upper()
    if max_length is not None:
        text = text[:max_length].strip()
    return text


def safe_float(value: object, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def format_float(value: object, fallback: str = "0.00") -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return fallback


def truncate_text(value: object, max_length: int = 60) -> str:
    text = str(value)
    return text if len(text) <= max_length else f"{text[: max_length - 3]}..."


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def iso_to_display_date(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    return parsed.strftime("%d/%m/%Y") if parsed else ""


def iso_to_display_time(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    return parsed.strftime("%H:%M:%S") if parsed else ""


def parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "si", "yes"}


def center_window(root, width: int, height: int) -> None:
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x_position = int((screen_width - width) / 2)
    y_position = int((screen_height - height) / 2)
    root.geometry(f"{width}x{height}+{x_position}+{y_position}")
