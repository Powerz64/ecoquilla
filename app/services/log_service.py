from __future__ import annotations


class LogService:
    """Centralized structured logging for the desktop application."""

    def __init__(self, log_repository):
        self.log_repository = log_repository

    def log(
        self,
        level: str,
        user: str,
        action: str,
        detail: str,
        *,
        session_id: str = "",
    ) -> None:
        self.log_repository.add(
            user,
            action,
            detail,
            level=level.upper(),
            session_id=session_id,
        )

    def info(self, user: str, action: str, detail: str, *, session_id: str = "") -> None:
        self.log("INFO", user, action, detail, session_id=session_id)

    def warning(self, user: str, action: str, detail: str, *, session_id: str = "") -> None:
        self.log("WARNING", user, action, detail, session_id=session_id)

    def error(self, user: str, action: str, detail: str, *, session_id: str = "") -> None:
        self.log("ERROR", user, action, detail, session_id=session_id)

    def list_logs(self, filter_text: str = "") -> list[dict]:
        return self.log_repository.list_all(filter_text)
