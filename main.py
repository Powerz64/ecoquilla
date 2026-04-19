from __future__ import annotations

import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

try:
    import matplotlib
except ImportError:  # pragma: no cover
    matplotlib = None
else:
    matplotlib.use("TkAgg")

from app.config import APP_COPYRIGHT, APP_DATA_DIR, APP_NAME, APP_VERSION, COLORS, ICON_FILE
from app.data.database import SQLiteDatabase
from app.data.repositories import (
    LoginAttemptRepository,
    LogRepository,
    RecordRepository,
    SessionRepository,
    UserRepository,
)
from app.services.analytics_service import AnalyticsService
from app.services.auth_service import AuthService
from app.services.log_service import LogService
from app.services.record_service import RecordService
from app.services.system_service import SystemService
from app.services.update_service import UpdateService
from app.services.user_service import UserService
from app.ui.login_view import LoginView
from app.ui.main_view import MainView


def apply_window_icon(window: tk.Misc) -> None:
    if not ICON_FILE.exists():
        return
    try:
        window.iconbitmap(default=str(ICON_FILE))
    except tk.TclError:
        pass


class SplashScreen:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.overrideredirect(True)
        self.window.configure(bg=COLORS["bg_dark"])
        self.window.attributes("-topmost", True)
        apply_window_icon(self.window)

        outer = tk.Frame(
            self.window,
            bg=COLORS["shadow"],
            padx=2,
            pady=2,
        )
        outer.pack(fill="both", expand=True)

        card = tk.Frame(
            outer,
            bg=COLORS["bg_panel"],
            padx=26,
            pady=24,
            highlightthickness=1,
            highlightbackground=COLORS["border"],
        )
        card.pack(fill="both", expand=True)

        brand_row = tk.Frame(card, bg=COLORS["bg_panel"])
        brand_row.pack(fill="x", pady=(0, 10))

        logo = tk.Label(
            brand_row,
            text="E",
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            font=("Segoe UI", 18, "bold"),
            width=2,
            height=1,
        )
        logo.pack(side="left", padx=(0, 12))

        text_col = tk.Frame(brand_row, bg=COLORS["bg_panel"])
        text_col.pack(side="left", fill="both", expand=True)

        tk.Label(
            text_col,
            text="ECOQUILLA",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            text_col,
            text="Sistema de gestión inteligente",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            card,
            text=f"{APP_COPYRIGHT} · v{APP_VERSION}",
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(anchor="w")

        self._center(430, 178)

    def destroy(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()

    def _center(self, width: int, height: int) -> None:
        self.window.update_idletasks()
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = max((screen_width - width) // 2, 0)
        y = max((screen_height - height) // 2, 0)
        self.window.geometry(f"{width}x{height}+{x}+{y}")


class WindowStateManager:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.state_file = APP_DATA_DIR / "window_state.txt"
        self._save_after_id: str | None = None
        self._restoring = False
        self.root.resizable(True, True)
        self.root.bind("<Configure>", self._on_configure, add="+")

    def apply(self) -> None:
        self.root.resizable(True, True)
        self._restoring = True

        state = "zoomed"
        geometry = ""
        if self.state_file.exists():
            loaded_state, loaded_geometry = self._read_state()
            state = loaded_state or "zoomed"
            geometry = loaded_geometry

        try:
            if geometry:
                self.root.geometry(geometry)
        except tk.TclError:
            geometry = ""

        def finish_restore() -> None:
            try:
                if state == "zoomed":
                    self.root.state("zoomed")
                else:
                    self.root.state("normal")
                    if geometry:
                        self.root.geometry(geometry)
            except tk.TclError:
                try:
                    self.root.state("zoomed")
                except tk.TclError:
                    pass
            finally:
                self._restoring = False
                self._persist_state()

        self.root.after_idle(finish_restore)

    def install_close_handler(self, callback) -> None:
        def on_close() -> None:
            self._persist_state()
            callback()

        self.root.protocol("WM_DELETE_WINDOW", on_close)

    def _read_state(self) -> tuple[str, str]:
        try:
            raw = self.state_file.read_text(encoding="utf-8").splitlines()
        except OSError:
            return "", ""

        state = ""
        geometry = ""
        for line in raw:
            if line.startswith("state="):
                state = line.split("=", 1)[1].strip()
            elif line.startswith("geometry="):
                geometry = line.split("=", 1)[1].strip()
        return state, geometry

    def _on_configure(self, event) -> None:
        if event.widget is not self.root or self._restoring:
            return
        if self._save_after_id:
            self.root.after_cancel(self._save_after_id)
        self._save_after_id = self.root.after(150, self._persist_state)

    def _persist_state(self) -> None:
        self._save_after_id = None
        try:
            state = self.root.state()
            if state not in {"normal", "zoomed"}:
                state = "normal"
            geometry = self.root.winfo_geometry()
            self.state_file.write_text(
                f"state={state}\ngeometry={geometry}\n",
                encoding="utf-8",
            )
        except (OSError, tk.TclError):
            pass


class EcoQuillaDesktop:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.title(APP_NAME)
        apply_window_icon(self.root)
        self.window_state = WindowStateManager(self.root)

        self.database = SQLiteDatabase()
        self.user_repository = UserRepository(self.database)
        self.record_repository = RecordRepository(self.database)
        self.log_repository = LogRepository(self.database)
        self.attempt_repository = LoginAttemptRepository(self.database)
        self.session_repository = SessionRepository(self.database)
        self.user_repository.ensure_defaults()

        self.log_service = LogService(self.log_repository)
        self.auth_service = AuthService(
            user_repository=self.user_repository,
            attempt_repository=self.attempt_repository,
            session_repository=self.session_repository,
            log_service=self.log_service,
        )
        self.record_service = RecordService(
            record_repository=self.record_repository,
            log_service=self.log_service,
        )
        self.user_service = UserService(
            user_repository=self.user_repository,
            log_service=self.log_service,
        )
        self.analytics_service = AnalyticsService()
        self.system_service = SystemService(
            record_repository=self.record_repository,
            user_repository=self.user_repository,
            session_repository=self.session_repository,
            log_service=self.log_service,
        )
        self.update_service = UpdateService(log_service=self.log_service)

        self._show_login()

    def _clear_root(self) -> None:
        for widget in self.root.winfo_children():
            widget.destroy()

    def _show_login(self) -> None:
        self._clear_root()
        self.current_view = LoginView(
            root=self.root,
            auth_service=self.auth_service,
            user_service=self.user_service,
            on_login_success=self._show_main_app,
        )
        apply_window_icon(self.root)
        self.window_state.apply()
        self.window_state.install_close_handler(self.root.destroy)

    def _show_main_app(
        self,
        username: str,
        role: str,
        session_id: str,
        expires_at: str,
    ) -> None:
        self._clear_root()
        self.current_view = MainView(
            root=self.root,
            username=username,
            role=role,
            session_id=session_id,
            session_expires_at=expires_at,
            auth_service=self.auth_service,
            record_service=self.record_service,
            user_service=self.user_service,
            analytics_service=self.analytics_service,
            system_service=self.system_service,
            update_service=self.update_service,
            on_logout=self._show_login,
        )
        apply_window_icon(self.root)
        self.window_state.apply()
        self.window_state.install_close_handler(self.current_view._exit_application)


def _write_startup_log(error: Exception) -> Path | None:
    log_file = APP_DATA_DIR / "startup_error.log"
    try:
        log_file.write_text(
            "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            encoding="utf-8",
        )
    except OSError:
        return None
    return log_file


def _show_startup_error(root: tk.Tk, error: Exception) -> None:
    log_file = _write_startup_log(error)
    detail = "No se pudo iniciar la aplicación."
    if log_file:
        detail += f"\n\nSe guardó un registro en:\n{log_file}"
    try:
        messagebox.showerror(
            f"{APP_NAME} - Error de inicio",
            detail,
            parent=root,
        )
    except tk.TclError:
        pass


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    root.configure(bg=COLORS["bg_dark"])
    root.resizable(True, True)
    apply_window_icon(root)
    splash = SplashScreen(root)

    def start_app() -> None:
        try:
            EcoQuillaDesktop(root)
            splash.destroy()
            root.deiconify()
            root.focus_force()
        except Exception as error:
            splash.destroy()
            _show_startup_error(root, error)
            root.destroy()

    root.after(1500, start_app)
    root.mainloop()


if __name__ == "__main__":
    main()
