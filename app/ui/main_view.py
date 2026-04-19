from __future__ import annotations

import queue
import threading
import tkinter as tk
from datetime import datetime
from types import SimpleNamespace
from tkinter import filedialog, messagebox, ttk

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
except ImportError:  # pragma: no cover
    plt = None
    FigureCanvasTkAgg = None

from app.config import (
    APP_COPYRIGHT,
    APP_LOCATION,
    APP_NAME,
    APP_VERSION,
    COLORS,
    FONT_KPI,
    FONT_MINI,
    FONT_SUB,
    FONT_TITLE,
    FONT_TEXT,
    MATERIAL_COLORS,
    VALID_RESIDUES,
    VALID_ROLES,
    VALID_ZONES,
    UPDATE_CHECK_ON_START,
    apply_plot_theme,
    clear_skipped_update_version,
    get_skipped_update_version,
    set_skipped_update_version,
)
from app.core.exceptions import DataStoreError
from app.core.utils import now_timestamp, parse_iso_datetime, truncate_text
from app.ui.widgets import SmartButton, Tooltip, separator


class MainView:
    def __init__(
        self,
        root,
        username,
        role,
        session_id,
        session_expires_at,
        auth_service,
        record_service,
        user_service,
        analytics_service,
        system_service,
        update_service,
        on_logout,
    ):
        self.root = root
        self.username = username
        self.role = role
        self.current_user = SimpleNamespace(role=role, username=username)
        self.session_id = session_id
        self.session_expires_at = session_expires_at
        self.auth_service = auth_service
        self.record_service = record_service
        self.user_service = user_service
        self.analytics_service = analytics_service
        self.system_service = system_service
        self.update_service = update_service
        self.on_logout = on_logout

        self.selected_index: int | None = None
        self.chart_canvases = []
        self.chart_frames: dict[str, tk.Frame] = {}
        self.chart_cards: dict[str, tk.Frame] = {}
        self.dashboard_tab = None
        self.records_tab = None
        self.users_tab = None
        self.insights_body = None
        self.kpi_labels: dict[str, tk.Label] = {}
        self.kpi_cards: dict[str, tk.Frame] = {}
        self.kpi_shadows: dict[str, tk.Frame] = {}
        self.kpi_icons: dict[str, tk.Label] = {}
        self.kpi_titles: dict[str, tk.Label] = {}
        self.kpi_top_rows: dict[str, tk.Frame] = {}
        self.sidebar_nav_buttons: dict[str, dict[str, object]] = {}
        self.record_filter_chip_buttons: dict[str, SmartButton] = {}
        self.record_table_base_tags: dict[str, tuple[str, ...]] = {}
        self.hovered_record_item: str | None = None
        self.latest_records: list[dict] = []
        self.latest_kpis: dict[str, int | float] = {}
        self.content_frame: tk.Frame | None = None
        self.operator_content: tk.Frame | None = None
        self.primary_actions_section: tk.Frame | None = None
        self.kpi_section: tk.Frame | None = None
        self.admin_current_view = ""
        self.operator_current_view = ""
        self.operator_primary_buttons: list[SmartButton] = []
        self.operator_primary_button: SmartButton | None = None
        self.operator_edit_mode = False
        self.operator_submit_in_progress = False
        self.operator_loaded_record_snapshot: dict[str, str] | None = None
        self.form_error_fields: set[str] = set()
        self.record_table = None
        self.record_status = None
        self.search_entry = None
        self.filter_status = None
        self.filter_residue = None
        self.filter_zone = None
        self.operator_record_empty_state = None
        self.record_table_action_column = None
        self.form_widgets = {}
        self.operator_validation_label = None
        self.operator_edit_label = None
        self.feedback_host = None
        self.feedback_label = None
        self.feedback_after_id = None
        self.pending_feedback: tuple[str, str] | None = None
        self.ui_job_queue: queue.Queue = queue.Queue()
        self.update_check_in_progress = False
        self.update_download_in_progress = False
        self.update_install_in_progress = False
        self.user_table = None
        self.user_form = {}
        self.selected_kpi_key = "total"
        self.session_expired_notified = False
        self.space_xs = 4
        self.space_sm = 8
        self.space_md = 16
        self.space_lg = 24
        self.space_xl = 32
        self.sidebar_bg = "#0b1220"
        self.sidebar_card_bg = "#0b1220"
        self.sidebar_hover_bg = "#0f172a"
        self.sidebar_active_bg = "#1f2937"
        self.sidebar_border = "#162033"
        self.sidebar_text_primary = "#e5e7eb"
        self.sidebar_text_secondary = "#9ca3af"
        self.sidebar_accent = "#22c55e"
        self.active_sidebar_key: str | None = None

        self.is_admin = self.current_user.role == "ADMIN"
        self.is_operator = self.current_user.role == "OPERADOR"
        self.can_edit_records = self.current_user.role in {"ADMIN", "OPERADOR"}
        self.can_delete_records = self.current_user.role == "ADMIN"
        self.can_manage_users = self.current_user.role == "ADMIN"
        self.charts_enabled = plt is not None and FigureCanvasTkAgg is not None

        if self.charts_enabled:
            apply_plot_theme(plt)

        self.root.title(f"{APP_COPYRIGHT} - {APP_NAME}")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.geometry("1600x930")
        self.root.minsize(1440, 820)
        self.root.protocol("WM_DELETE_WINDOW", self._exit_application)

        self._setup_style()
        self._build_layout()
        self._refresh_all()
        self.root.after(120, self._process_ui_job_queue)
        if UPDATE_CHECK_ON_START:
            self.root.after(1500, self._check_updates_on_start)

    def _setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Treeview",
            background=COLORS["bg_card"],
            foreground=COLORS["text_primary"],
            fieldbackground=COLORS["bg_soft"],
            rowheight=46,
            borderwidth=0,
            font=FONT_TEXT,
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["bg_soft"],
            foreground=COLORS["accent"],
            font=("Consolas", 9, "bold"),
            relief="flat",
            padding=(10, 10),
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["selected"])],
            foreground=[("selected", "white")],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", COLORS["hover"])],
            foreground=[("active", COLORS["text_primary"])],
        )
        style.configure(
            "Operator.Treeview",
            background="#1f2f46",
            foreground=COLORS["text_primary"],
            fieldbackground="#1f2f46",
            rowheight=32,
            borderwidth=0,
            font=("Consolas", 9),
            padding=6,
        )
        style.configure(
            "Operator.Treeview.Heading",
            background="#16253a",
            foreground=COLORS["text_primary"],
            font=("Consolas", 9, "bold"),
            relief="flat",
            padding=(12, 10),
        )
        style.map(
            "Operator.Treeview",
            background=[("selected", "#2e4a6b")],
            foreground=[("selected", "white")],
        )
        style.map(
            "Operator.Treeview.Heading",
            background=[("active", "#1a2c44")],
            foreground=[("active", COLORS["text_primary"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["bg_row"],
            background=COLORS["bg_row"],
            foreground=COLORS["text_primary"],
            selectbackground=COLORS["selected"],
            arrowcolor=COLORS["accent"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["bg_row"])],
            foreground=[("readonly", COLORS["text_primary"])],
        )
        style.configure(
            "Invalid.TCombobox",
            fieldbackground=COLORS["bg_row"],
            background=COLORS["bg_row"],
            foreground=COLORS["text_primary"],
            selectbackground=COLORS["selected"],
            arrowcolor=COLORS["accent_red"],
            bordercolor=COLORS["accent_red"],
            lightcolor=COLORS["accent_red"],
            darkcolor=COLORS["accent_red"],
        )
        style.map(
            "Invalid.TCombobox",
            fieldbackground=[("readonly", COLORS["bg_row"])],
            foreground=[("readonly", COLORS["text_primary"])],
        )
        style.configure("TNotebook", background=COLORS["bg_dark"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=COLORS["bg_panel"],
            foreground=COLORS["text_secondary"],
            font=("Consolas", 9, "bold"),
            padding=[16, 8],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", COLORS["bg_card"])],
            foreground=[("selected", COLORS["accent"])],
        )

    def _build_layout(self):
        self.sidebar = tk.Frame(self.root, bg=self.sidebar_bg, width=235)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        self.main = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self.main.pack(side="right", fill="both", expand=True)

        self._build_sidebar()
        self._build_header()
        if self.is_admin:
            self._build_primary_actions()
            self._build_kpis()
            self.content_frame = tk.Frame(self.main, bg=COLORS["bg_dark"])
            self.content_frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))
            self.render_admin_dashboard()
        else:
            self._build_operator_workspace()
            self._set_active_sidebar("records")
        self._build_footer()

    def _create_elevated_card(self, parent, *, bg_key: str = "bg_card", border_key: str = "border"):
        shadow = tk.Frame(parent, bg=COLORS["shadow"], bd=0, highlightthickness=0)
        card = tk.Frame(
            shadow,
            bg=COLORS[bg_key],
            highlightbackground=COLORS[border_key],
            highlightthickness=1,
            bd=0,
        )
        card.pack(fill="both", expand=True, padx=(0, 3), pady=(0, 3))
        return shadow, card

    def _set_view_loading(self, container, loading: bool):
        if container is None:
            return
        try:
            container.configure(cursor="watch" if loading else "")
            self.root.update()
        except tk.TclError:
            return

    def _clear_feedback_banner(self):
        if self.feedback_after_id is not None:
            try:
                self.root.after_cancel(self.feedback_after_id)
            except tk.TclError:
                pass
            self.feedback_after_id = None
        if self.feedback_label is not None and self.feedback_label.winfo_exists():
            self.feedback_label.destroy()
        self.feedback_label = None

    def _set_feedback_host(self, host):
        self._clear_feedback_banner()
        self.feedback_host = host
        self._render_pending_feedback()

    def _queue_feedback(self, text: str, tone: str = "success"):
        self.pending_feedback = (text, tone)

    def _render_pending_feedback(self):
        if self.pending_feedback is None or self.feedback_host is None:
            return
        if not self.feedback_host.winfo_exists():
            return
        text, tone = self.pending_feedback
        self.pending_feedback = None
        self._show_inline_feedback(text, tone=tone)

    def _show_inline_feedback(self, text: str, *, tone: str = "success"):
        if self.feedback_host is None or not self.feedback_host.winfo_exists():
            self.pending_feedback = (text, tone)
            return
        self._clear_feedback_banner()
        palette = {
            "success": ("#022c22", "#4ade80"),
            "warning": ("#3b2f0d", "#facc15"),
            "error": ("#3f1d1d", "#f87171"),
            "info": ("#102a43", "#60a5fa"),
        }
        bg, fg = palette.get(tone, palette["info"])
        self.feedback_label = tk.Label(
            self.feedback_host,
            text=text,
            bg=bg,
            fg=fg,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=10,
            pady=6,
        )
        self.feedback_label.pack(fill="x", pady=(0, 8))
        self.feedback_after_id = self.root.after(3000, self._clear_feedback_banner)

    def _sync_update_busy_state(self):
        self._set_view_loading(
            self.root,
            self.update_check_in_progress
            or self.update_download_in_progress
            or self.update_install_in_progress,
        )

    def _process_ui_job_queue(self):
        try:
            while True:
                callback, args, kwargs = self.ui_job_queue.get_nowait()
                callback(*args, **kwargs)
        except queue.Empty:
            pass
        finally:
            if self.root.winfo_exists():
                self.root.after(120, self._process_ui_job_queue)

    def _check_updates_on_start(self):
        if not self._ensure_session_active(notify=False):
            return
        self._start_update_check(silent=True)

    def _check_updates_manually(self):
        if not self._ensure_session_active():
            return
        self._start_update_check(silent=False)

    def _start_update_check(self, *, silent: bool):
        if silent and not self.update_service.is_configured():
            return
        if self.update_check_in_progress or self.update_download_in_progress:
            if not silent:
                messagebox.showinfo("Actualizaciones", "Ya hay una comprobacion de actualizaciones en curso.")
            return

        self.update_check_in_progress = True
        self._sync_update_busy_state()
        if not silent:
            self._set_status("Buscando actualizaciones...", COLORS["accent_blue"])

        def worker():
            result = self.update_service.check_for_updates(
                actor=self.username,
                session_id=self.session_id,
            )
            self.ui_job_queue.put((self._finish_update_check, (result,), {"silent": silent}))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_check(self, result, *, silent: bool):
        self.update_check_in_progress = False
        self._sync_update_busy_state()

        if not result.ok:
            if not silent:
                self._set_status(result.message, COLORS["accent_red"])
                messagebox.showerror("Actualizaciones", result.message)
            return

        if not result.update_available:
            if not silent:
                self._set_status(f"Ya tienes la version mas reciente ({APP_VERSION})", COLORS["success"])
                messagebox.showinfo("Actualizaciones", f"Ya tienes la version mas reciente ({APP_VERSION}).")
            return

        skipped_version = get_skipped_update_version()
        if silent and skipped_version and skipped_version == result.latest_version:
            return

        self._set_status(f"Nueva version disponible: {result.latest_version}", COLORS["accent_blue"])
        self._prompt_install_update(result)

    def _prompt_install_update(self, result):
        skipped_note = ""
        if get_skipped_update_version() == result.latest_version:
            skipped_note = "\n\nEsta version fue omitida previamente."
        message = (
            f"Nueva version disponible: {result.latest_version}\n"
            f"Version actual: {APP_VERSION}\n\n"
            "Si eliges Si se descargara e instalara ahora.\n"
            "Si eliges No esta version se omitira y no se volvera a mostrar automaticamente.\n"
            "Cancelar la pospondra sin omitirla."
        )
        if result.notes:
            message += f"\n\nNotas de la version:\n{result.notes}"
        message += skipped_note

        decision = messagebox.askyesnocancel(
            "Actualizacion disponible",
            message,
            icon="info",
            parent=self.root,
        )
        if decision is None:
            self._set_status("Actualizacion pospuesta por el usuario", COLORS["warning"])
            return
        if decision is False:
            set_skipped_update_version(result.latest_version)
            self._set_status(f"Version {result.latest_version} omitida", COLORS["warning"])
            return

        clear_skipped_update_version()
        self._start_update_download(
            result.download_url,
            latest_version=result.latest_version,
            expected_sha256=result.sha256,
        )

    def _start_update_download(self, url: str, *, latest_version: str, expected_sha256: str = ""):
        if self.update_download_in_progress or self.update_install_in_progress:
            messagebox.showinfo("Actualizaciones", "Ya hay una descarga de actualizacion en progreso.")
            return

        self.update_download_in_progress = True
        self._sync_update_busy_state()
        self._update_download_progress(latest_version, 0)

        def worker():
            result = self.update_service.download_update(
                url,
                latest_version=latest_version,
                expected_sha256=expected_sha256,
                actor=self.username,
                session_id=self.session_id,
                progress_callback=lambda percent: self.ui_job_queue.put(
                    (self._update_download_progress, (latest_version, percent), {})
                ),
            )
            self.ui_job_queue.put((self._finish_update_download, (result,), {"latest_version": latest_version}))

        threading.Thread(target=worker, daemon=True).start()

    def _update_download_progress(self, latest_version: str, percent: int | None):
        base_text = f"Descargando actualizacion {latest_version}..."
        if percent is None:
            self._set_status(base_text, COLORS["accent_blue"])
            return
        bounded_percent = max(0, min(int(percent), 100))
        self._set_status(f"{base_text} {bounded_percent}%", COLORS["accent_blue"])

    def _finish_update_download(self, result, *, latest_version: str):
        self.update_download_in_progress = False
        self._sync_update_busy_state()

        if not result.ok:
            self._set_status(result.message, COLORS["accent_red"])
            messagebox.showerror("Actualizaciones", result.message)
            return

        self._start_update_install(result.file_path, latest_version=latest_version)

    def _start_update_install(self, file_path: str, *, latest_version: str):
        self.update_install_in_progress = True
        self._sync_update_busy_state()
        self._set_status(f"Instalando actualizacion {latest_version}...", COLORS["success"])

        def worker():
            result = self.update_service.install_update(
                file_path,
                actor=self.username,
                session_id=self.session_id,
            )
            self.ui_job_queue.put((self._finish_update_install, (result,), {"latest_version": latest_version}))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_update_install(self, result, *, latest_version: str):
        self.update_install_in_progress = False
        self._sync_update_busy_state()
        if not result.ok:
            self._set_status(result.message, COLORS["accent_red"])
            messagebox.showerror("Actualizaciones", result.message)
            return

        clear_skipped_update_version()
        self._set_status(f"Instalando actualizacion {latest_version}...", COLORS["success"])
        self.auth_service.register_exit(self.session_id, self.username)
        self.root.withdraw()
        self.root.after(1000, self.root.destroy)

    def _build_tone_chip(self, parent, text: str, *, bg_key: str = "bg_soft", fg_key: str = "text_secondary"):
        chip = tk.Label(
            parent,
            text=text,
            font=("Consolas", 7, "bold"),
            bg=COLORS[bg_key],
            fg=COLORS[fg_key],
            padx=10,
            pady=4,
        )
        chip.pack(side="left", padx=(0, self.space_sm))
        return chip

    def _build_operator_actions(self):
        action_bar = tk.Frame(self.main, bg=COLORS["bg_dark"])
        action_bar.pack(fill="x", padx=18, pady=(0, 14))

        shadow, card = self._create_elevated_card(action_bar)
        shadow.pack(fill="x")

        body = tk.Frame(card, bg=COLORS["bg_card"])
        body.pack(fill="x", padx=16, pady=16)

        left = tk.Frame(body, bg=COLORS["bg_card"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text="Panel operativo",
            font=("Consolas", 16, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Registra actividad, revisa registros y mantén la operación al día.",
            font=("Consolas", 9),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(4, 0))

        SmartButton(
            body,
            "Nuevo registro",
            self._open_record_form,
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            hover=COLORS["accent_dim"],
            pressed=COLORS["accent_dim"],
            font=("Consolas", 11, "bold"),
            padx=18,
            pady=9,
        ).pack(side="right")

    def _build_operator_workspace(self):
        workspace = tk.Frame(self.main, bg=COLORS["bg_dark"])
        workspace.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        intro_shadow, intro = self._create_elevated_card(workspace)
        intro_shadow.pack(fill="x", pady=(0, 14))

        intro_body = tk.Frame(intro, bg=COLORS["bg_card"])
        intro_body.pack(fill="x", padx=18, pady=18)

        intro_left = tk.Frame(intro_body, bg=COLORS["bg_card"])
        intro_left.pack(side="left", fill="x", expand=True)
        tk.Label(
            intro_left,
            text="Panel operativo",
            font=("Consolas", 18, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            intro_left,
            text="Registro de reciclaje rápido",
            font=("Consolas", 10, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        ).pack(anchor="w", pady=(6, 0))
        tk.Label(
            intro_left,
            text="Completa los campos para registrar un nuevo residuo.",
            font=("Consolas", 9),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(6, 0))
        self.operator_primary_button = None
        self.operator_content = tk.Frame(workspace, bg=COLORS["bg_dark"])
        self.operator_content.pack(fill="both", expand=True)
        self.render_operator_form_view()

    def _clear_operator_content(self):
        if self.operator_content is None:
            return
        for widget in self.operator_content.winfo_children():
            widget.destroy()
        self.operator_primary_buttons = []
        self.form_widgets = {}
        self.record_table = None
        self.record_status = None
        self.search_entry = None
        self.filter_status = None
        self.filter_residue = None
        self.filter_zone = None
        self.operator_record_empty_state = None
        self.record_table_action_column = None
        self.operator_validation_label = None
        self.operator_edit_label = None
        self.feedback_host = None
        self.record_table_base_tags.clear()
        self.hovered_record_item = None

    def _clear_admin_content(self):
        if self.content_frame is None:
            return
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        self.dashboard_tab = None
        self.records_tab = None
        self.users_tab = None
        self.chart_canvases = []
        self.chart_frames = {}
        self.chart_cards = {}
        self.insights_body = None
        self.record_table = None
        self.record_status = None
        self.search_entry = None
        self.filter_status = None
        self.filter_residue = None
        self.filter_zone = None
        self.operator_record_empty_state = None
        self.record_table_action_column = None
        self.form_widgets = {}
        self.feedback_host = None
        self.user_table = None
        self.user_form = {}
        self.record_table_base_tags.clear()
        self.hovered_record_item = None

    def render_admin_dashboard(self):
        if not self.is_admin or self.content_frame is None:
            return
        self._set_view_loading(self.content_frame, True)
        try:
            self._set_admin_dashboard_chrome(True)
            self._clear_admin_content()
            self.admin_current_view = "dashboard"
            self._set_active_sidebar("dashboard")

            self.dashboard_tab = tk.Frame(self.content_frame, bg=COLORS["bg_dark"])
            self.dashboard_tab.pack(fill="both", expand=True)
            self._build_dashboard_tab()
            self._set_feedback_host(None)

            records = self.latest_records or self._load_records()
            self.latest_records = list(records)
            self._refresh_dashboard(records)
        finally:
            self._set_view_loading(self.content_frame, False)

    def render_admin_records(self):
        if not self.is_admin or self.content_frame is None:
            return
        self._set_view_loading(self.content_frame, True)
        try:
            self._set_admin_dashboard_chrome(False)
            self._clear_admin_content()
            self.admin_current_view = "records"
            self._set_active_sidebar("records")

            self.records_tab = tk.Frame(self.content_frame, bg=COLORS["bg_dark"])
            self.records_tab.pack(fill="both", expand=True)

            intro_shadow, intro = self._create_elevated_card(self.records_tab)
            intro_shadow.pack(fill="x", pady=(0, 10))
            intro_left = tk.Frame(intro, bg=COLORS["bg_card"])
            intro_left.pack(side="left", fill="x", expand=True, padx=16, pady=14)
            tk.Label(
                intro_left,
                text="Registros del sistema",
                font=("Consolas", 12, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_primary"],
            ).pack(anchor="w")
            tk.Label(
                intro_left,
                text="Consulta, filtra y gestiona el historial completo sin mezclarlo con el formulario.",
                font=("Consolas", 8),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", pady=(4, 0))

            feedback_host = tk.Frame(self.records_tab, bg=COLORS["bg_dark"])
            feedback_host.pack(fill="x")
            self._set_feedback_host(feedback_host)

            table_host = tk.Frame(self.records_tab, bg=COLORS["bg_dark"])
            table_host.pack(fill="both", expand=True)
            self._build_record_table(table_host)
            self._refresh_record_table()
        finally:
            self._set_view_loading(self.content_frame, False)

    def render_admin_new_record(self):
        if not self.is_admin or self.content_frame is None:
            return
        self._set_view_loading(self.content_frame, True)
        try:
            self._set_admin_dashboard_chrome(False)
            self._clear_admin_content()
            self.admin_current_view = "new_record"
            self._set_active_sidebar("new_record")

            page = tk.Frame(self.content_frame, bg=COLORS["bg_dark"])
            page.pack(fill="both", expand=True, padx=20, pady=20)

            title_block = tk.Frame(page, bg=COLORS["bg_dark"])
            title_block.pack(fill="x", pady=(0, 12))
            tk.Label(
                title_block,
                text="Nuevo registro",
                font=("Consolas", 14, "bold"),
                bg=COLORS["bg_dark"],
                fg=COLORS["text_primary"],
            ).pack(anchor="w")
            tk.Label(
                title_block,
                text="Completa todos los campos y crea un registro nuevo sin salir de esta vista.",
                font=("Consolas", 9),
                bg=COLORS["bg_dark"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", pady=(4, 0))

            form_host = tk.Frame(page, bg=COLORS["bg_dark"])
            form_host.pack(fill="both", expand=True)
            self._build_record_form(form_host)
            self._clear_form()
            self.root.after(80, self._focus_operator_form)
        finally:
            self._set_view_loading(self.content_frame, False)

    def render_admin_users(self):
        if not self.can_manage_users or self.content_frame is None:
            return
        self._set_admin_dashboard_chrome(False)
        self._clear_admin_content()
        self.admin_current_view = "users"
        self._set_active_sidebar("users")

        self.users_tab = tk.Frame(self.content_frame, bg=COLORS["bg_dark"])
        self.users_tab.pack(fill="both", expand=True)
        self._build_users_tab()
        self._refresh_user_table()

    def render_operator_form_view(self):
        if not self.is_operator or self.operator_content is None:
            return
        self._set_view_loading(self.operator_content, True)
        try:
            self._clear_operator_content()
            self.operator_current_view = "form"
            self._set_active_sidebar("new_record")
            self._sync_operator_primary_button()

            form_host = tk.Frame(self.operator_content, bg=COLORS["bg_dark"])
            form_host.pack(fill="both", expand=True, pady=(0, 8))
            self._build_record_form(form_host, operator_mode=True)
            self._clear_form()
            self.root.after(80, self._focus_operator_form)
        finally:
            self._set_view_loading(self.operator_content, False)

    def render_operator_table_view(self):
        if not self.is_operator or self.operator_content is None:
            return
        self._set_view_loading(self.operator_content, True)
        try:
            self._clear_operator_content()
            self.operator_current_view = "records"
            self._set_active_sidebar("records")
            self._sync_operator_primary_button()

            feedback_host = tk.Frame(self.operator_content, bg=COLORS["bg_dark"])
            feedback_host.pack(fill="x")
            self._set_feedback_host(feedback_host)

            table_host = tk.Frame(self.operator_content, bg=COLORS["bg_dark"])
            table_host.pack(fill="both", expand=True, pady=(0, 4))
            self._build_record_table(table_host, operator_mode=True)
            self._refresh_record_table()
        finally:
            self._set_view_loading(self.operator_content, False)

    def _build_sidebar(self):
        self.sidebar_nav_buttons.clear()
        top = tk.Frame(self.sidebar, bg=self.sidebar_bg)
        top.pack(fill="x", padx=16, pady=(16, 0))

        brand_frame = tk.Frame(top, bg=self.sidebar_bg)
        brand_frame.pack(fill="x")

        row_frame = tk.Frame(brand_frame, bg=self.sidebar_bg)
        row_frame.pack(fill="x")

        logo_label = tk.Label(
            row_frame,
            text="E",
            font=("Segoe UI", 11, "bold"),
            width=2,
            bg=self.sidebar_hover_bg,
            fg=self.sidebar_accent,
            anchor="center",
            padx=4,
            pady=4,
        )
        logo_label.pack(side="left", padx=(0, 12))

        text_frame = tk.Frame(row_frame, bg=self.sidebar_bg)
        text_frame.pack(side="left", fill="x", expand=True)

        tk.Label(
            text_frame,
            text="ECOQUILLA",
            font=("Segoe UI", 13, "bold"),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_primary,
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            text_frame,
            text="Gestión inteligente de reciclaje",
            font=("Segoe UI", 8),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
            anchor="w",
            wraplength=0,
        ).pack(anchor="w", pady=(1, 0))

        separator(top, bg=self.sidebar_border).pack(fill="x", pady=(12, 12))

        nav_area = tk.Frame(self.sidebar, bg=self.sidebar_bg)
        nav_area.pack(fill="both", expand=True, padx=16, pady=(0, 0))

        if self.is_admin:
            self._build_sidebar_group(
                nav_area,
                "DASHBOARD",
                [
                    ("dashboard", "Resumen ejecutivo", self._open_dashboard, None, "Ver metricas y graficas principales"),
                ],
            )
            self._build_sidebar_group(
                nav_area,
                "REGISTROS",
                [
                    ("records", "Registros", self._open_records, None, "Ir a la tabla de registros"),
                    ("new_record", "Nuevo registro", self._open_new_record, COLORS["accent"], "Crear un registro nuevo"),
                    (None, "Importar", self._import_csv, None, "Cargar registros desde CSV o JSON"),
                    (None, "Exportar CSV", self._export_csv, COLORS["accent_purple"], "Exportar registros filtrados"),
                    (None, "Exportar JSON", self._export_json, None, "Exportar registros filtrados a JSON"),
                ],
            )
            self._build_sidebar_group(
                nav_area,
                "USUARIOS",
                [
                    ("users", "Gestionar usuarios", self._open_users, None, "Administrar usuarios y permisos"),
                ],
            )
            self._build_sidebar_group(
                nav_area,
                "SISTEMA",
                [
                    (None, "Recargar datos", self._refresh_all, None, "Actualizar datos desde SQLite"),
                    (None, "Buscar actualizaciones", self._check_updates_manually, None, "Buscar una nueva versión disponible"),
                    (None, "Auditoría", self._open_audit_window, COLORS["accent_blue"], "Ver eventos del sistema"),
                    (None, "Backup", self._create_backup, None, "Generar copia de seguridad"),
                    (
                        None,
                        "Desinstalar aplicación",
                        self._confirm_uninstall_application,
                        COLORS["accent_red"],
                        "Eliminar la aplicación y todos sus datos locales",
                    ),
                ],
            )
        elif self.is_operator:
            self._build_sidebar_group(
                nav_area,
                "OPERACIÓN",
                [
                    ("records", "Registros", self._open_records, None, "Ir a la tabla de registros"),
                    ("new_record", "Nuevo registro", self._open_record_form, COLORS["accent"], "Crear un registro nuevo"),
                    (None, "Recargar datos", self._refresh_all, None, "Actualizar datos desde SQLite"),
                ],
            )

        self._build_profile_card(nav_area)

        bottom = tk.Frame(self.sidebar, bg=self.sidebar_bg)
        bottom.pack(side="bottom", fill="x", padx=16, pady=10)

        separator(bottom, bg=self.sidebar_border).pack(fill="x", pady=(0, 8))

        logout_label = tk.Label(
            bottom,
            text="Cerrar sesión",
            font=("Segoe UI", 10),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
            anchor="w",
            cursor="hand2",
            pady=4,
        )
        logout_label.pack(fill="x")
        logout_label.bind("<Button-1>", lambda _event: self._logout())
        logout_label.bind("<Enter>", lambda _event: logout_label.config(fg=self.sidebar_text_primary, bg=self.sidebar_hover_bg))
        logout_label.bind("<Leave>", lambda _event: logout_label.config(fg=self.sidebar_text_secondary, bg=self.sidebar_bg))

        tk.Label(
            bottom,
            text=APP_LOCATION,
            font=("Segoe UI", 7),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
            anchor="w",
        ).pack(fill="x", pady=(6, 0))

    def _build_sidebar_group(self, parent, title: str, items: list[tuple[str | None, str, object, str | None, str]]):
        group = tk.Frame(parent, bg=self.sidebar_bg)
        group.pack(fill="x", pady=(0, 6))
        tk.Label(
            group,
            text=title.upper(),
            font=("Segoe UI", 8, "bold"),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
        ).pack(anchor="w", pady=(0, 4))
        for nav_key, text, command, color, tip in items:
            button = self._sidebar_button(group, text, command, color=color, nav_key=nav_key)
            button.pack(fill="x", pady=(0, 1))
            Tooltip(button, tip)

    def _build_profile_card(self, parent):
        users = self.user_service.list_users()
        current_user = users.get(self.username, {})
        display_name = current_user.get("nombre_completo") or self.username.title()

        separator(parent, bg=self.sidebar_border).pack(fill="x", pady=(10, 10))

        row = tk.Frame(parent, bg=self.sidebar_bg)
        row.pack(fill="x", pady=(0, 4))

        avatar = tk.Canvas(
            row,
            width=28,
            height=28,
            bg=self.sidebar_bg,
            highlightthickness=0,
        )
        avatar.pack(side="left", padx=(0, 10))
        avatar.create_oval(2, 2, 26, 26, fill=self.sidebar_hover_bg, outline="")
        avatar.create_text(14, 14, text=(display_name[:1] or self.username[:1]).upper(), fill=self.sidebar_text_primary, font=("Segoe UI", 10, "bold"))

        info = tk.Frame(row, bg=self.sidebar_bg)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(
            info,
            text=display_name,
            font=("Segoe UI", 10, "bold"),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_primary,
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            info,
            text=self._role_label(self.role),
            font=("Segoe UI", 8),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
            anchor="w",
        ).pack(fill="x", pady=(1, 0))

    def _sidebar_button(self, parent, text, command, color=None, nav_key: str | None = None):
        wrapper = tk.Frame(parent, bg=self.sidebar_bg, cursor="hand2")
        row = tk.Frame(
            wrapper,
            bg=self.sidebar_bg,
            highlightthickness=1,
            highlightbackground=self.sidebar_bg,
            cursor="hand2",
        )
        row.pack(fill="x")

        label = tk.Label(
            row,
            text=text,
            font=("Segoe UI", 10),
            bg=self.sidebar_bg,
            fg=self.sidebar_text_secondary,
            anchor="w",
            padx=8,
            pady=4,
            cursor="hand2",
        )
        label.pack(side="left", fill="x", expand=True)

        item = {
            "wrapper": wrapper,
            "row": row,
            "label": label,
            "accent": color,
            "active": False,
        }

        def handle_click(_=None):
            self._run_sidebar_action(command)

        def handle_enter(_=None):
            self._paint_sidebar_item(item, hovered=True)

        def handle_leave(_=None):
            self._paint_sidebar_item(item, hovered=False)

        for widget in (wrapper, row, label):
            widget.bind("<Button-1>", handle_click)
            widget.bind("<Enter>", handle_enter)
            widget.bind("<Leave>", handle_leave)

        if nav_key:
            self.sidebar_nav_buttons[nav_key] = item
        return wrapper

    def _paint_sidebar_item(self, item: dict[str, object], hovered: bool = False):
        active = bool(item.get("active"))
        if active:
            card_bg = self.sidebar_active_bg
            label_fg = "#ffffff"
            border = self.sidebar_active_bg
            font = ("Segoe UI", 10, "bold")
        else:
            card_bg = self.sidebar_hover_bg if hovered else self.sidebar_bg
            border = self.sidebar_hover_bg if hovered else self.sidebar_bg
            font = ("Segoe UI", 10)
            label_fg = self.sidebar_text_primary if hovered else self.sidebar_text_secondary

        row = item["row"]
        label = item["label"]
        row.configure(bg=card_bg, highlightbackground=border)
        label.configure(bg=card_bg, fg=label_fg, font=font)

    def _run_sidebar_action(self, command):
        busy_targets = [self.root, self.sidebar, self.main]
        try:
            for widget in busy_targets:
                try:
                    widget.configure(cursor="watch")
                except tk.TclError:
                    pass
            try:
                self.root.update()
            except tk.TclError:
                pass
            command()
            try:
                self.root.focus_force()
            except tk.TclError:
                pass
        finally:
            for widget in busy_targets:
                try:
                    widget.configure(cursor="")
                except tk.TclError:
                    pass

    def _build_header(self):
        header = tk.Frame(self.main, bg=COLORS["bg_dark"])
        header.pack(fill="x", padx=18, pady=(18, 10))

        left = tk.Frame(header, bg=COLORS["bg_dark"])
        left.pack(side="left", fill="x", expand=True)
        title_text = "PANEL EJECUTIVO - GESTION DE RECICLAJE" if self.is_admin else "PANEL OPERATIVO"
        subtitle_text = "Sistema cargado correctamente" if self.is_admin else "Vista restringida para operación y registro"
        tk.Label(
            left,
            text=title_text,
            font=("Consolas", 20, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w")
        self.header_status = tk.Label(
            left,
            text=subtitle_text,
            font=FONT_SUB,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        )
        self.header_status.pack(anchor="w", pady=(4, 0))

        right = tk.Frame(header, bg=COLORS["bg_dark"])
        right.pack(side="right")
        clock_shadow, clock_card = self._create_elevated_card(right)
        clock_shadow.pack(anchor="e")
        tk.Label(
            clock_card,
            text="TIEMPO REAL",
            font=("Consolas", 7, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="e", padx=12, pady=(8, 0))
        self.clock_label = tk.Label(
            clock_card,
            text="",
            font=("Consolas", 11, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        )
        self.clock_label.pack(anchor="e", padx=12, pady=(2, 8))
        self._tick_clock()

    def _build_primary_actions(self):
        action_bar = tk.Frame(self.main, bg=COLORS["bg_dark"])
        action_bar.pack(fill="x", padx=18, pady=(0, 14))
        self.primary_actions_section = action_bar

        hero_shadow, callout = self._create_elevated_card(action_bar)
        hero_shadow.pack(fill="x")

        gradient_band = tk.Frame(callout, bg=COLORS["bg_card"])
        gradient_band.pack(fill="x", padx=16, pady=(12, 0))
        for width, color in ((54, COLORS["accent"]), (92, COLORS["accent_blue"]), (138, COLORS["accent_purple"])):
            tk.Frame(gradient_band, bg=color, width=width, height=4).pack(side="left", padx=(0, 6))

        content = tk.Frame(callout, bg=COLORS["bg_card"])
        content.pack(fill="x", padx=16, pady=(12, 16))

        accent_rail = tk.Frame(content, bg=COLORS["accent"], width=8)
        accent_rail.pack(side="left", fill="y", padx=(0, 16))

        left = tk.Frame(content, bg=COLORS["bg_card"])
        left.pack(side="left", fill="x", expand=True)
        self._build_tone_chip(left, "ECOQUILLA", bg_key="accent_blue", fg_key="text_primary")
        tk.Label(
            left,
            text="ECOQUILLA - Sistema de Gestion Inteligente",
            font=("Consolas", 18, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w", pady=(10, 0))
        tk.Label(
            left,
            text="Monitorea, analiza y optimiza el reciclaje en tiempo real.",
            font=("Consolas", 10),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(6, 0))

        chip_row = tk.Frame(left, bg=COLORS["bg_card"])
        chip_row.pack(anchor="w", pady=(12, 0))
        for text in ("Panel ejecutivo", "Alertas inteligentes", "Operación en vivo"):
            self._build_tone_chip(chip_row, text)

        actions = tk.Frame(content, bg=COLORS["bg_card"])
        actions.pack(side="right", padx=(16, 0), anchor="center")
        SmartButton(
            actions,
            "Importar datos",
            self._import_csv,
            bg=COLORS["bg_soft"],
            fg=COLORS["text_primary"],
            hover=COLORS["hover"],
            pressed=COLORS["selected"],
            font=("Consolas", 10, "bold"),
            padx=18,
            pady=9,
        ).pack(fill="x", pady=(10, 0))

    def _open_dashboard(self):
        if self.is_admin:
            self.render_admin_dashboard()
        else:
            self._open_records()

    def _open_records(self):
        if self.is_operator:
            self.render_operator_table_view()
            return
        if self.is_admin:
            self.render_admin_records()
        elif hasattr(self, "form_widgets") and "usuario" in self.form_widgets:
            self._set_active_sidebar("records")
            self.form_widgets["usuario"].focus_set()

    def _open_new_record(self):
        if self.is_operator:
            self.render_operator_form_view()
            self._clear_form()
            return
        if self.is_admin:
            self.render_admin_new_record()
            return
        self._open_record_form()

    def _open_users(self):
        if self.can_manage_users:
            self.render_admin_users()

    def _set_admin_dashboard_chrome(self, visible: bool):
        if not self.is_admin or self.content_frame is None:
            return

        sections = [
            (self.primary_actions_section, {"fill": "x", "padx": 18, "pady": (0, 14), "before": self.content_frame}),
            (self.kpi_section, {"fill": "x", "padx": 18, "pady": (0, 10), "before": self.content_frame}),
        ]

        for section, pack_kwargs in sections:
            if section is None or not section.winfo_exists():
                continue
            if visible:
                if not section.winfo_manager():
                    section.pack(**pack_kwargs)
            elif section.winfo_manager():
                section.pack_forget()

    def _role_label(self, role: str) -> str:
        return {
            "ADMIN": "Administrador",
            "OPERADOR": "Operador",
            "LECTURA": "Solo lectura",
        }.get(role, role.title())

    def _set_active_sidebar(self, key: str):
        self.active_sidebar_key = key
        for nav_key, item in self.sidebar_nav_buttons.items():
            item["active"] = nav_key == key
            self._paint_sidebar_item(item, hovered=False)

    def _sync_sidebar_selection(self, _=None):
        if not hasattr(self, "notebook"):
            if self.is_admin:
                active_key = self.admin_current_view or "dashboard"
            else:
                active_key = "records"
            self._set_active_sidebar(active_key)
            return
        current_tab = self.notebook.index(self.notebook.select())
        mapping = {0: "dashboard", 1: "records", 2: "users"} if self.is_admin else {0: "records"}
        active_key = mapping.get(current_tab, "dashboard")
        if active_key in self.sidebar_nav_buttons:
            self._set_active_sidebar(active_key)

    def _tick_clock(self):
        self.clock_label.config(text=now_timestamp().replace("T", " "))
        self._update_session_status()
        if self.session_id and not self.auth_service.is_session_active(self.session_id):
            if not self.session_expired_notified:
                self.session_expired_notified = True
                messagebox.showwarning("SESION EXPIRADA", "La sesion expiro. Debes iniciar sesion de nuevo.")
                self.on_logout()
            return
        self.root.after(1000, self._tick_clock)

    def _build_kpis(self):
        section = tk.Frame(self.main, bg=COLORS["bg_dark"])
        section.pack(fill="x", padx=18, pady=(0, 10))
        self.kpi_section = section

        tk.Label(
            section,
            text="Centro de decision",
            font=("Consolas", 10, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 8))
        tk.Label(
            section,
            text="Empieza por los KPIs. Haz clic sobre cualquiera para ver un desglose inmediato.",
            font=("Consolas", 8),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(0, 10))

        self.kpi_frame = tk.Frame(section, bg=COLORS["bg_dark"])
        self.kpi_frame.pack(fill="x")
        specs = [
            ("total", "\U0001f4e6", "TOTAL", COLORS["accent_blue"]),
            ("valid", "\u2714", "VALIDOS", COLORS["success"]),
            ("errors", "\u274c", "ERRORES", COLORS["accent_red"]),
            ("today", "◷", "HOY", COLORS["accent_yellow"]),
            ("residue_types", "◫", "TIPOS", COLORS["accent_purple"]),
            ("efficiency_pct", "\u26a1", "EFICIENCIA", COLORS["success"]),
            ("alerts", "\u26a0", "ALERTAS", COLORS["warning"]),
            ("total_kg", "KG", "TOTAL KG", COLORS["accent_orange"]),
        ]

        for column, (key, icon, title, color) in enumerate(specs):
            shadow, card = self._create_elevated_card(self.kpi_frame)
            shadow.grid(row=0, column=column, sticky="nsew", padx=6, pady=2)
            self.kpi_frame.grid_columnconfigure(column, weight=1)
            top = tk.Frame(card, bg=COLORS["bg_card"])
            top.pack(fill="x", padx=16, pady=(14, 0))
            icon_label = tk.Label(
                top,
                text=icon,
                font=("Consolas", 12, "bold"),
                bg=COLORS["bg_soft"],
                fg=color,
                width=3,
                pady=4,
            )
            icon_label.pack(side="left")
            title_label = tk.Label(
                top,
                text=title,
                font=("Consolas", 7, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            )
            title_label.pack(side="left", padx=(10, 0), pady=(4, 0))
            value = tk.Label(card, text="-", font=("Consolas", 30, "bold"), bg=COLORS["bg_card"], fg=color)
            value.pack(anchor="w", padx=16, pady=(12, 14))
            self.kpi_labels[key] = value
            self.kpi_cards[key] = card
            self.kpi_shadows[key] = shadow
            self.kpi_icons[key] = icon_label
            self.kpi_titles[key] = title_label
            self.kpi_top_rows[key] = top
            self._bind_kpi_card(card, key, top, icon_label, title_label, value)

        self._build_kpi_detail_panel(section)

    def _bind_kpi_card(self, card, key: str, *widgets):
        for widget in (card, *widgets):
            widget.bind("<Button-1>", lambda _event, metric_key=key: self._show_kpi_detail(metric_key))
            widget.configure(cursor="hand2")

            widget.bind("<Enter>", lambda _event, metric_key=key: self._hover_kpi(metric_key, True))
            widget.bind("<Leave>", lambda _event, metric_key=key: self._hover_kpi(metric_key, False))

    def _hover_kpi(self, key: str, active: bool):
        if key == self.selected_kpi_key or key not in self.kpi_cards:
            return
        card = self.kpi_cards[key]
        top = self.kpi_top_rows.get(key)
        bg = COLORS["bg_soft"] if active else COLORS["bg_card"]
        border = COLORS["accent_blue"] if active else COLORS["border"]
        card.configure(bg=bg, highlightbackground=border)
        if top is not None:
            top.configure(bg=bg)
        if key in self.kpi_titles:
            self.kpi_titles[key].config(bg=bg)
        if key in self.kpi_labels:
            self.kpi_labels[key].config(bg=bg)

    def _build_kpi_detail_panel(self, parent):
        shadow, self.kpi_detail_card = self._create_elevated_card(parent)
        shadow.pack(fill="x", pady=(12, 0))

        header = tk.Frame(self.kpi_detail_card, bg=COLORS["bg_card"])
        header.pack(fill="x", padx=16, pady=(14, 0))
        self.kpi_detail_title = tk.Label(
            header,
            text="Detalle del KPI",
            font=("Consolas", 11, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        )
        self.kpi_detail_title.pack(side="left")
        self.kpi_detail_badge = tk.Label(
            header,
            text="Resumen",
            font=("Consolas", 7, "bold"),
            bg=COLORS["bg_soft"],
            fg=COLORS["text_secondary"],
            padx=10,
            pady=4,
        )
        self.kpi_detail_badge.pack(side="right")

        self.kpi_detail_body = tk.Label(
            self.kpi_detail_card,
            text="Selecciona un KPI para ver su desglose.",
            justify="left",
            anchor="w",
            font=("Consolas", 8),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        )
        self.kpi_detail_body.pack(fill="x", padx=16, pady=(10, 14))

    def _build_tabs(self):
        self.notebook = ttk.Notebook(self.main)
        self.notebook.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        self.records_tab = tk.Frame(self.notebook, bg=COLORS["bg_dark"])
        if self.is_admin:
            self.dashboard_tab = tk.Frame(self.notebook, bg=COLORS["bg_dark"])
            self.users_tab = tk.Frame(self.notebook, bg=COLORS["bg_dark"])
            self.notebook.add(self.dashboard_tab, text="  DASHBOARD  ")
            self.notebook.add(self.records_tab, text="  REGISTROS  ")
            self.notebook.add(self.users_tab, text="  USUARIOS  ")
            self._build_dashboard_tab()
            self._build_records_tab()
            self._build_users_tab()
        else:
            self.dashboard_tab = None
            self.users_tab = None
            self.notebook.add(self.records_tab, text="  PANEL OPERATIVO  ")
            self._build_records_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self._sync_sidebar_selection)
        self._sync_sidebar_selection()

    def _build_dashboard_tab(self):
        intro_shadow, intro = self._create_elevated_card(self.dashboard_tab)
        intro_shadow.pack(fill="x", padx=12, pady=(12, 8))
        left = tk.Frame(intro, bg=COLORS["bg_card"])
        left.pack(side="left", fill="x", expand=True, padx=16, pady=14)
        tk.Label(
            left,
            text="Panel analitico",
            font=("Consolas", 11, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w")
        tk.Label(
            left,
            text="Visualiza tendencias, zonas y usuarios clave sin perder el foco operativo.",
            font=("Consolas", 8),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", pady=(4, 0))

        first_row = tk.Frame(self.dashboard_tab, bg=COLORS["bg_dark"])
        first_row.pack(fill="both", expand=True, padx=8, pady=8)

        second_row = tk.Frame(self.dashboard_tab, bg=COLORS["bg_dark"])
        second_row.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        chart_specs = [
            ("status", "ESTADO GENERAL", first_row, 0),
            ("residues", "TIPO DE RESIDUO", first_row, 1),
            ("days", "DIAS DE RECOLECCION", first_row, 2),
            ("users", "TOP USUARIOS", first_row, 3),
            ("zones", "TOTAL KG POR ZONA", second_row, 0),
            ("trend", "TENDENCIA SEMANAL", second_row, 1),
        ]
        for key, title, parent, column in chart_specs:
            shadow, container = self._create_elevated_card(parent)
            shadow.grid(row=0, column=column, sticky="nsew", padx=6, pady=6)
            parent.grid_columnconfigure(column, weight=1)
            parent.grid_rowconfigure(0, weight=1)

            title_row = tk.Frame(container, bg=COLORS["bg_card"])
            title_row.pack(fill="x", padx=12, pady=(12, 0))
            tk.Label(
                title_row,
                text=title,
                font=("Consolas", 9, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_primary"],
            ).pack(side="left")
            tk.Label(
                title_row,
                text="En vivo",
                font=("Consolas", 7, "bold"),
                bg=COLORS["bg_soft"],
                fg=COLORS["text_secondary"],
                padx=8,
                pady=2,
            ).pack(side="right")

            frame = tk.Frame(container, bg=COLORS["bg_card"])
            frame.pack(fill="both", expand=True, padx=8, pady=10)
            self.chart_frames[key] = frame
            self.chart_cards[key] = container

        insights_shadow, insights_card = self._create_elevated_card(self.dashboard_tab)
        insights_shadow.pack(fill="x", padx=12, pady=(0, 10))
        tk.Label(
            insights_card,
            text="INSIGHTS Y ALERTAS",
            font=("Consolas", 10, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        ).pack(anchor="w", padx=18, pady=(16, 0))
        tk.Label(
            insights_card,
            text="Lo importante primero. Usa estas recomendaciones para decidir tu siguiente accion.",
            justify="left",
            anchor="w",
            font=("Consolas", 8),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(fill="x", padx=18, pady=(6, 0))
        self.insights_body = tk.Frame(insights_card, bg=COLORS["bg_card"])
        self.insights_body.pack(fill="x", padx=14, pady=(10, 14))

    def _build_records_tab(self):
        if self.is_operator:
            operator_shadow, operator_intro = self._create_elevated_card(self.records_tab)
            operator_shadow.pack(fill="x", padx=8, pady=(8, 4))
            left_intro = tk.Frame(operator_intro, bg=COLORS["bg_card"])
            left_intro.pack(side="left", fill="x", expand=True, padx=16, pady=14)
            tk.Label(
                left_intro,
                text="Panel operativo",
                font=("Consolas", 12, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_primary"],
            ).pack(anchor="w")
            tk.Label(
                left_intro,
                text="Gestiona registros activos y crea nuevas entradas sin distracciones.",
                font=("Consolas", 8),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", pady=(4, 0))
            SmartButton(
                operator_intro,
                "Nuevo registro",
                self._open_record_form,
                bg=COLORS["accent"],
                fg=COLORS["bg_dark"],
                hover=COLORS["accent_dim"],
                pressed=COLORS["accent_dim"],
                font=("Consolas", 10, "bold"),
                padx=16,
                pady=8,
            ).pack(side="right", padx=(0, 16), pady=14)

        left = tk.Frame(self.records_tab, bg=COLORS["bg_dark"], width=330)
        left.pack(side="left", fill="y", padx=(8, 4), pady=8)
        left.pack_propagate(False)

        right = tk.Frame(self.records_tab, bg=COLORS["bg_dark"])
        right.pack(side="right", fill="both", expand=True, padx=(4, 8), pady=8)

        self._build_record_form(left)
        self._build_record_table(right)

    def _build_record_form(self, parent, *, operator_mode: bool = False):
        shadow, card = self._create_elevated_card(parent)
        shadow.pack(fill="both", expand=True)
        self._build_compact_record_form_layout(card, operator_mode=operator_mode)
        if not self.can_edit_records:
            self.button_save.lock()
            self.button_update.lock()
            self.button_clear.lock()
            self._set_form_state("disabled")
        if not self.can_delete_records:
            self.button_delete.lock()
        if operator_mode:
            self._set_operator_edit_mode(False)
            self.root.after(80, self._focus_operator_form)
        return

        tk.Label(
            card,
            text="REGISTRO DE RECICLAJE RÁPIDO" if operator_mode else "FORMULARIO DE REGISTRO",
            font=("Consolas", 14 if operator_mode else 11, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        ).pack(anchor="w", padx=20 if operator_mode else 16, pady=(18 if operator_mode else 16, 8 if operator_mode else 12))
        if operator_mode:
            tk.Label(
                card,
                text="Completa los campos para registrar un nuevo residuo.",
                font=("Consolas", 9),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", padx=20, pady=(0, 14))
            self.operator_validation_label = tk.Label(
                card,
                text="",
                font=("Consolas", 9, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["warning"],
            )
            self.operator_validation_label.pack(anchor="w", padx=20, pady=(0, 6))
            self.operator_edit_label = tk.Label(
                card,
                text="",
                font=("Consolas", 9, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["accent_yellow"],
            )
            self.operator_edit_label.pack(anchor="w", padx=20, pady=(0, 8))

        self.form_widgets = {}
        fields = (
            [
                ("USUARIO / NOMBRE", "usuario", "entry", None),
                ("DIRECCION", "direccion", "entry", None),
                ("ZONA", "zona", "combo", VALID_ZONES),
                ("TIPO DE RESIDUO", "residuo", "combo", VALID_RESIDUES),
                ("DIA RECOLECCION", "dia", "combo", ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]),
                ("PESO (KG)", "peso_kg", "entry", None),
                ("REGISTRADO", "registrado", "combo", ["SI", "NO"]),
                ("NOTAS", "notas", "entry", None),
            ]
            if operator_mode
            else [
                ("USUARIO / NOMBRE", "usuario", "entry", None),
                ("REGISTRADO", "registrado", "combo", ["SI", "NO"]),
                ("TIPO DE RESIDUO", "residuo", "combo", VALID_RESIDUES),
                ("ZONA", "zona", "combo", VALID_ZONES),
                ("DIRECCION", "direccion", "entry", None),
                ("DIA RECOLECCION", "dia", "combo", ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]),
                ("PESO (KG)", "peso_kg", "entry", None),
                ("NOTAS", "notas", "entry", None),
            ]
        )
        for label, key, field_type, options in fields:
            tk.Label(
                card,
                text=label,
                font=("Consolas", 9 if operator_mode else 8, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", padx=20 if operator_mode else 16, pady=((8 if operator_mode else 4), 0))
            if field_type == "entry":
                widget = tk.Entry(
                    card,
                    font=("Consolas", 11 if operator_mode else 10),
                    bg=COLORS["bg_row"],
                    fg=COLORS["text_primary"],
                    insertbackground=COLORS["accent"],
                    relief="flat",
                    bd=4,
                    highlightthickness=1,
                    highlightbackground=COLORS["border"],
                    highlightcolor=COLORS["border"],
                )
                widget.pack(fill="x", padx=20 if operator_mode else 16, ipady=8 if operator_mode else 4, pady=(4 if operator_mode else 2, 0))
            else:
                widget = ttk.Combobox(card, values=options, state="readonly", font=("Consolas", 11 if operator_mode else 10))
                widget.pack(fill="x", padx=20 if operator_mode else 16, pady=(4 if operator_mode else 2, 0), ipady=4 if operator_mode else 0)
                if key == "registrado":
                    widget.set("SI")
            self.form_widgets[key] = widget

        separator(card).pack(fill="x", padx=20 if operator_mode else 16, pady=14 if operator_mode else 12)

        if operator_mode:
            button_frame = tk.Frame(card, bg=COLORS["bg_card"])
            button_frame.pack(fill="x", padx=20, pady=(0, 10))

            self.button_save = SmartButton(
                button_frame,
                "CREAR REGISTRO",
                self._submit_operator_record,
                bg=COLORS["accent"],
                fg=COLORS["bg_dark"],
                height=2,
                font=("Consolas", 11, "bold"),
                pady=8,
            )
            self.button_save.pack(fill="x")

            actions_frame = tk.Frame(card, bg=COLORS["bg_card"])
            actions_frame.pack(fill="x", padx=20, pady=(0, 16))

            self.button_update = SmartButton(
                actions_frame,
                "ACTUALIZAR",
                self._update_record,
                bg=COLORS["accent_yellow"],
                fg=COLORS["bg_dark"],
                width=13,
                height=2,
            )

            self.button_clear = SmartButton(
                actions_frame,
                "CANCELAR",
                self._cancel_record_edit,
                bg=COLORS["accent_blue"],
                fg="white",
                width=13,
                height=2,
            )
            self.button_clear.pack(side="left", fill="x", expand=True, padx=(0, 6))

            self.button_delete = SmartButton(
                actions_frame,
                "ELIMINAR",
                self._delete_record,
                bg=COLORS["accent_red"],
                fg="white",
                width=13,
                height=2,
            )
            self.button_delete.pack(side="left", fill="x", expand=True, padx=(6, 0))
            self.button_delete.pack_forget()
        else:
            grid = tk.Frame(card, bg=COLORS["bg_card"])
            grid.pack(fill="x", padx=12, pady=(0, 12))

            self.button_save = SmartButton(
                grid,
                "CREAR REGISTRO",
                self._save_record,
                bg=COLORS["accent"],
                fg=COLORS["bg_dark"],
                width=13,
                height=2,
                font=("Consolas", 10, "bold"),
            )
            self.button_save.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

            self.button_update = SmartButton(
                grid,
                "ACTUALIZAR",
                self._update_record,
                bg=COLORS["accent_yellow"],
                fg=COLORS["bg_dark"],
                width=13,
                height=2,
            )
            self.button_update.grid(row=0, column=1, padx=4, pady=4)

            self.button_clear = SmartButton(
                grid,
                "LIMPIAR",
                self._clear_form,
                bg=COLORS["accent_blue"],
                fg="white",
                width=13,
                height=2,
            )
            self.button_clear.grid(row=1, column=0, padx=4, pady=4, sticky="ew")

            self.button_delete = SmartButton(
                grid,
                "ELIMINAR",
                self._delete_record,
                bg=COLORS["accent_red"],
                fg="white",
                width=13,
                height=2,
            )
            self.button_delete.grid(row=1, column=1, padx=4, pady=4, sticky="ew")

        if not self.can_edit_records:
            self.button_save.lock()
            self.button_update.lock()
            self.button_clear.lock()
            self._set_form_state("disabled")
        if not self.can_delete_records:
            self.button_delete.lock()
        if operator_mode:
            self._set_operator_edit_mode(False)
            self.root.after(80, self._focus_operator_form)

    def _build_compact_record_form_layout(self, card, *, operator_mode: bool):
        tk.Label(
            card,
            text="REGISTRO DE RECICLAJE RAPIDO" if operator_mode else "FORMULARIO DE REGISTRO",
            font=("Consolas", 13, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        ).pack(anchor="w", padx=20, pady=(5, 2))

        tk.Label(
            card,
            text="Completa los campos para registrar un nuevo residuo.",
            font=("Consolas", 9),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        feedback_host = tk.Frame(card, bg=COLORS["bg_card"])
        feedback_host.pack(fill="x", padx=20)
        self._set_feedback_host(feedback_host)

        self.operator_validation_label = tk.Label(
            card,
            text="",
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["warning"],
        )
        self.operator_validation_label.pack(anchor="w", padx=20, pady=(0, 4))

        self.operator_edit_label = tk.Label(
            card,
            text="",
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent_yellow"],
        )
        self.operator_edit_label.pack(anchor="w", padx=20, pady=(0, 6))

        self.form_widgets = {}
        form_frame = tk.Frame(card, bg=COLORS["bg_card"])
        form_frame.pack(fill="both", expand=True, padx=20, pady=8)
        form_frame.columnconfigure(0, weight=1)
        form_frame.columnconfigure(1, weight=1)

        field_rows = [
            (
                ("USUARIO / NOMBRE", "usuario", "entry", None),
                ("DIRECCION", "direccion", "entry", None),
            ),
            (
                ("ZONA", "zona", "combo", VALID_ZONES),
                ("TIPO DE RESIDUO", "residuo", "combo", VALID_RESIDUES),
            ),
            (
                ("DIA RECOLECCION", "dia", "combo", ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"]),
                ("PESO (KG)", "peso_kg", "entry", None),
            ),
            (
                ("REGISTRADO", "registrado", "combo", ["SI", "NO"]),
                ("NOTAS", "notas", "entry", None),
            ),
        ]

        for block_index, pair in enumerate(field_rows):
            label_row = block_index * 2
            input_row = label_row + 1
            for column, (label, key, field_type, options) in enumerate(pair):
                pad_x = (0, 6) if column == 0 else (6, 0)
                tk.Label(
                    form_frame,
                    text=label,
                    font=("Consolas", 8, "bold"),
                    bg=COLORS["bg_card"],
                    fg=COLORS["text_secondary"],
                    anchor="w",
                ).grid(row=label_row, column=column, sticky="w", padx=pad_x, pady=(0, 2))

                if field_type == "entry":
                    widget = tk.Entry(
                        form_frame,
                        font=("Consolas", 10),
                        bg=COLORS["bg_row"],
                        fg=COLORS["text_primary"],
                        insertbackground=COLORS["accent"],
                        relief="flat",
                        bd=4,
                        highlightthickness=1,
                        highlightbackground=COLORS["border"],
                        highlightcolor=COLORS["border"],
                    )
                    widget.grid(row=input_row, column=column, sticky="ew", padx=pad_x, pady=(0, 8), ipady=6)
                else:
                    widget = ttk.Combobox(
                        form_frame,
                        values=options,
                        state="readonly",
                        font=("Consolas", 10),
                    )
                    widget.grid(row=input_row, column=column, sticky="ew", padx=pad_x, pady=(0, 8), ipady=3)
                    if key == "registrado":
                        widget.set("SI")

                self.form_widgets[key] = widget

        submit_row = 8
        actions_row = 9
        form_frame.grid_rowconfigure(submit_row, weight=1)
        self.button_save = SmartButton(
            form_frame,
            "CREAR REGISTRO",
            self._submit_operator_record if operator_mode else self._save_record,
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            height=2,
            font=("Consolas", 11, "bold"),
            pady=8,
        )
        self.button_save.grid(
            row=submit_row,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 0),
        )

        actions_frame = tk.Frame(form_frame, bg=COLORS["bg_card"])
        actions_frame.grid(row=actions_row, column=0, columnspan=2, sticky="ew", pady=(8, 2))

        if operator_mode:
            actions_frame.columnconfigure(0, weight=1)
            actions_frame.columnconfigure(1, weight=1)
            self.button_update = SmartButton(
                actions_frame,
                "ACTUALIZAR",
                self._update_record,
                bg=COLORS["accent_yellow"],
                fg=COLORS["bg_dark"],
                width=13,
                height=2,
            )
            self.button_clear = SmartButton(
                actions_frame,
                "CANCELAR",
                self._cancel_record_edit,
                bg=COLORS["bg_soft"],
                fg=COLORS["text_primary"],
                width=13,
                height=2,
            )
            self.button_clear.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.button_delete = SmartButton(
                actions_frame,
                "ELIMINAR",
                self._delete_record,
                bg=COLORS["accent_red"],
                fg="white",
                width=13,
                height=2,
            )
            self.button_delete.grid(row=0, column=1, sticky="ew", padx=(6, 0))
            self.button_delete.grid_remove()
        else:
            actions_frame.columnconfigure(0, weight=1)
            actions_frame.columnconfigure(1, weight=1)
            actions_frame.columnconfigure(2, weight=1)
            self.button_update = SmartButton(
                actions_frame,
                "ACTUALIZAR",
                self._update_record,
                bg=COLORS["accent_blue"],
                fg="white",
                height=2,
            )
            self.button_update.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self.button_clear = SmartButton(
                actions_frame,
                "CANCELAR",
                self._open_records,
                bg=COLORS["bg_soft"],
                fg=COLORS["text_primary"],
                height=2,
            )
            self.button_clear.grid(row=0, column=1, sticky="ew", padx=6)
            self.button_delete = SmartButton(
                actions_frame,
                "ELIMINAR",
                self._delete_record,
                bg=COLORS["accent_red"],
                fg="white",
                height=2,
            )
            self.button_delete.grid(row=0, column=2, sticky="ew", padx=(6, 0))

    def _build_operator_record_form_layout(self, card):
        title_label = tk.Label(
            card,
            text="REGISTRO DE RECICLAJE RÁPIDO",
            font=("Consolas", 13, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        )
        title_label.pack(anchor="w", padx=20, pady=(5, 2))

        subtitle_label = tk.Label(
            card,
            text="Completa los campos para registrar un nuevo residuo.",
            font=("Consolas", 9),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        )
        subtitle_label.pack(anchor="w", padx=20, pady=(0, 4))

        self.operator_validation_label = tk.Label(
            card,
            text="",
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["warning"],
        )
        self.operator_validation_label.pack(anchor="w", padx=20, pady=(0, 4))

        self.operator_edit_label = tk.Label(
            card,
            text="",
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent_yellow"],
        )
        self.operator_edit_label.pack(anchor="w", padx=20, pady=(0, 6))

        self.form_widgets = {}
        form_frame = tk.Frame(card, bg=COLORS["bg_card"])
        form_frame.pack(fill="x", padx=20, pady=8)
        form_frame.columnconfigure(0, weight=1)
        form_frame.columnconfigure(1, weight=1)

        operator_fields = [
            ("USUARIO / NOMBRE", "usuario", "entry", None, 0, 0, 2),
            ("DIRECCION", "direccion", "entry", None, 2, 0, 2),
            ("ZONA", "zona", "combo", VALID_ZONES, 4, 0, 1),
            ("TIPO DE RESIDUO", "residuo", "combo", VALID_RESIDUES, 4, 1, 1),
            ("DIA RECOLECCION", "dia", "combo", ["LUNES", "MARTES", "MIERCOLES", "JUEVES", "VIERNES", "SABADO", "DOMINGO"], 6, 0, 1),
            ("PESO (KG)", "peso_kg", "entry", None, 6, 1, 1),
            ("REGISTRADO", "registrado", "combo", ["SI", "NO"], 8, 0, 1),
            ("NOTAS", "notas", "entry", None, 10, 0, 2),
        ]

        for label, key, field_type, options, row, column, columnspan in operator_fields:
            if columnspan == 2:
                pad_x = 0
            elif column == 0:
                pad_x = (0, 6)
            else:
                pad_x = (6, 0)

            tk.Label(
                form_frame,
                text=label,
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
                anchor="w",
            ).grid(row=row, column=column, columnspan=columnspan, sticky="w", padx=pad_x, pady=(2, 2))

            if field_type == "entry":
                widget = tk.Entry(
                    form_frame,
                    font=("Consolas", 10),
                    bg=COLORS["bg_row"],
                    fg=COLORS["text_primary"],
                    insertbackground=COLORS["accent"],
                    relief="flat",
                    bd=4,
                    highlightthickness=1,
                    highlightbackground=COLORS["border"],
                    highlightcolor=COLORS["border"],
                )
                widget.grid(
                    row=row + 1,
                    column=column,
                    columnspan=columnspan,
                    sticky="ew",
                    padx=pad_x,
                    pady=(0, 4),
                    ipady=4,
                )
            else:
                widget = ttk.Combobox(
                    form_frame,
                    values=options,
                    state="readonly",
                    font=("Consolas", 10),
                )
                widget.grid(
                    row=row + 1,
                    column=column,
                    columnspan=columnspan,
                    sticky="ew",
                    padx=pad_x,
                    pady=(0, 4),
                    ipady=2,
                )
                if key == "registrado":
                    widget.set("SI")

            self.form_widgets[key] = widget

        divider = separator(form_frame)
        divider.grid(row=12, column=0, columnspan=2, sticky="ew", pady=(3, 6))

        actions_frame = tk.Frame(form_frame, bg=COLORS["bg_card"])
        actions_frame.grid(row=13, column=0, columnspan=2, sticky="ew", pady=(0, 2))
        actions_frame.columnconfigure(0, weight=1)
        actions_frame.columnconfigure(1, weight=1)

        self.button_update = SmartButton(
            actions_frame,
            "ACTUALIZAR",
            self._update_record,
            bg=COLORS["accent_yellow"],
            fg=COLORS["bg_dark"],
            width=13,
            height=2,
        )

        self.button_clear = SmartButton(
            actions_frame,
            "CANCELAR",
            self._cancel_record_edit,
            bg=COLORS["accent_blue"],
            fg="white",
            width=13,
            height=2,
        )
        self.button_clear.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.button_delete = SmartButton(
            actions_frame,
            "ELIMINAR",
            self._delete_record,
            bg=COLORS["accent_red"],
            fg="white",
            width=13,
            height=2,
        )
        self.button_delete.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.button_delete.grid_remove()
        if self.operator_primary_button is not None and self.operator_primary_button.winfo_exists():
            self.button_save = self.operator_primary_button

    def _build_record_table(self, parent, *, operator_mode: bool = False):
        if not operator_mode:
            filters_shadow, filters = self._create_elevated_card(parent)
            filters_shadow.pack(fill="x", pady=(0, 8))

            header = tk.Frame(filters, bg=COLORS["bg_card"])
            header.pack(fill="x", padx=14, pady=(12, 0))
            tk.Label(
                header,
                text="VISTA OPERATIVA DE REGISTROS",
                font=("Consolas", 10, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_primary"],
            ).pack(side="left")
            self._build_tone_chip(header, "Filtros rapidos", bg_key="bg_soft", fg_key="text_secondary")

            search_row = tk.Frame(filters, bg=COLORS["bg_card"])
            search_row.pack(fill="x", padx=14, pady=(12, 0))

            self.search_entry = tk.Entry(
                search_row,
                width=28,
                font=("Consolas", 10),
                bg=COLORS["bg_row"],
                fg=COLORS["text_primary"],
                insertbackground=COLORS["accent"],
                relief="flat",
                bd=4,
            )
            self.search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 12))
            self.search_entry.bind("<KeyRelease>", lambda _: self._refresh_record_table())

            SmartButton(
                search_row,
                "LIMPIAR FILTROS",
                self._reset_filters,
                bg=COLORS["bg_soft"],
                fg=COLORS["text_primary"],
            ).pack(side="right")

            filter_row = tk.Frame(filters, bg=COLORS["bg_card"])
            filter_row.pack(fill="x", padx=14, pady=(12, 0))
            tk.Label(filter_row, text="ESTADO:", font=("Consolas", 8, "bold"), bg=COLORS["bg_card"], fg=COLORS["text_secondary"]).pack(side="left")
            self.filter_status = self._build_filter_combo(filter_row, ["TODOS", "VALIDO", "ERROR"])
            tk.Label(filter_row, text="RESIDUO:", font=("Consolas", 8, "bold"), bg=COLORS["bg_card"], fg=COLORS["text_secondary"]).pack(side="left", padx=(14, 2))
            self.filter_residue = self._build_filter_combo(filter_row, ["TODOS"] + VALID_RESIDUES)
            tk.Label(filter_row, text="ZONA:", font=("Consolas", 8, "bold"), bg=COLORS["bg_card"], fg=COLORS["text_secondary"]).pack(side="left", padx=(14, 2))
            self.filter_zone = self._build_filter_combo(filter_row, ["TODAS"] + VALID_ZONES)
            self.filter_residue.bind("<<ComboboxSelected>>", lambda _: self._sync_residue_filter_chips(), add="+")

            chip_row = tk.Frame(filters, bg=COLORS["bg_card"])
            chip_row.pack(fill="x", padx=14, pady=(12, 14))
            tk.Label(
                chip_row,
                text="CHIPS:",
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(side="left", padx=(0, 8))
            self._build_residue_chips(chip_row)
        else:
            self.search_entry = None
            self.filter_status = None
            self.filter_residue = None
            self.filter_zone = None

        table_shadow, table_frame = self._create_elevated_card(parent)
        table_shadow.pack(fill="both", expand=True)

        title_row = tk.Frame(table_frame, bg=COLORS["bg_card"])
        title_row.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(
            title_row,
            text="MIS REGISTROS RECIENTES" if operator_mode else "REGISTROS",
            font=("Consolas", 11 if operator_mode else 10, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(side="left")
        if operator_mode:
            tk.Label(
                title_row,
                text="Últimos movimientos",
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_soft"],
                fg=COLORS["text_secondary"],
                padx=10,
                pady=4,
            ).pack(side="right")

        if operator_mode:
            operator_search_row = tk.Frame(table_frame, bg=COLORS["bg_card"])
            operator_search_row.pack(fill="x", padx=16, pady=(12, 6))
            tk.Label(
                operator_search_row,
                text="BUSCAR:",
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(side="left", padx=(0, 10))
            self.search_entry = tk.Entry(
                operator_search_row,
                width=30,
                font=("Consolas", 10),
                bg=COLORS["bg_row"],
                fg=COLORS["text_primary"],
                insertbackground=COLORS["accent"],
                relief="flat",
                bd=4,
            )
            self.search_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 12))
            self.search_entry.bind("<KeyRelease>", lambda _: self._refresh_record_table())
            SmartButton(
                operator_search_row,
                "LIMPIAR",
                self._reset_filters,
                bg=COLORS["bg_soft"],
                fg=COLORS["text_primary"],
            ).pack(side="right")

        self.record_table_mode = "operator" if operator_mode else "admin"
        columns = (
            ("residuo", "zona", "direccion", "dia", "peso_kg", "estado", "acciones")
            if operator_mode
            else (
                "usuario",
                "registrado",
                "residuo",
                "zona",
                "direccion",
                "dia",
                "peso_kg",
                "estado",
                "fecha",
                "creado_por",
                "notas",
            )
        )
        self.record_table = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            style="Operator.Treeview" if operator_mode else "Treeview",
        )
        headers = {
            "usuario": "USUARIO",
            "registrado": "REGISTRADO",
            "residuo": "RESIDUO",
            "zona": "ZONA",
            "direccion": "DIRECCION",
            "dia": "DIA",
            "peso_kg": "PESO KG",
            "estado": "ESTADO",
            "fecha": "FECHA",
            "creado_por": "REGISTRADO POR",
            "notas": "NOTAS",
            "acciones": "ACCIONES",
        }
        widths = {
            "usuario": 130,
            "registrado": 90,
            "residuo": 100,
            "zona": 105,
            "direccion": 220,
            "dia": 100,
            "peso_kg": 80,
            "estado": 90,
            "fecha": 90,
            "creado_por": 120,
            "notas": 180,
        }
        operator_widths = {
            "residuo": 120,
            "zona": 120,
            "direccion": 260,
            "dia": 120,
            "peso_kg": 120,
            "estado": 120,
            "acciones": 160,
        }
        for column in columns:
            self.record_table.heading(column, text=headers[column], anchor="center")
            width_map = operator_widths if operator_mode else widths
            if column == "direccion":
                self.record_table.column(column, width=width_map[column], anchor="w", stretch=True)
            else:
                self.record_table.column(column, width=width_map[column], anchor="center")
        self.record_table_action_column = f"#{len(columns)}" if operator_mode else None

        self.record_table.tag_configure("row_even", background="#1f2f46")
        self.record_table.tag_configure("row_odd", background="#243652")
        self.record_table.tag_configure("valid", foreground=COLORS["accent"])
        self.record_table.tag_configure("error", foreground=COLORS["accent_red"])
        self.record_table.tag_configure("hover_row", background="#2a3f5f")

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.record_table.yview)
        self.record_table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.operator_record_empty_state = None
        if operator_mode:
            self.operator_record_empty_state = tk.Label(
                table_frame,
                text="Aún no tienes registros",
                font=("Consolas", 10, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
                justify="center",
                pady=18,
            )
        self.record_table.pack(fill="both", expand=True, padx=12, pady=(12, 12))
        self.record_table.bind("<<TreeviewSelect>>", self._load_selected_record)
        self.record_table.bind("<ButtonRelease-1>", self._handle_record_table_click, add="+")
        self.record_table.bind("<Motion>", self._on_record_table_motion)
        self.record_table.bind("<Leave>", self._clear_record_row_hover)

        self.record_status = tk.Label(
            parent,
            text="",
            font=("Consolas", 8),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        )
        self.record_status.pack(anchor="w", padx=4, pady=2)
        if not operator_mode:
            self._sync_residue_filter_chips()

    def _build_filter_combo(self, parent, values):
        combo = ttk.Combobox(parent, values=values, state="readonly", width=11, font=("Consolas", 9))
        combo.pack(side="left", padx=(8, 0))
        combo.set(values[0])
        combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_record_table())
        return combo

    def _build_residue_chips(self, parent):
        self.record_filter_chip_buttons.clear()
        chip_specs = [("TODOS", "Todos")]
        chip_specs.extend((value, value.title()) for value in VALID_RESIDUES)
        for value, label in chip_specs:
            button = SmartButton(
                parent,
                label,
                lambda selected=value: self._set_residue_chip_filter(selected),
                bg=COLORS["bg_soft"],
                fg=COLORS["text_secondary"],
                hover=COLORS["hover"],
                pressed=COLORS["selected"],
                font=("Consolas", 8, "bold"),
                padx=10,
                pady=4,
            )
            button.pack(side="left", padx=(0, 8))
            self.record_filter_chip_buttons[value] = button

    def _set_residue_chip_filter(self, residue: str):
        self.filter_residue.set(residue)
        self._sync_residue_filter_chips()
        self._refresh_record_table()

    def _sync_residue_filter_chips(self):
        if not hasattr(self, "filter_residue") or self.filter_residue is None:
            return
        current = self.filter_residue.get() or "TODOS"
        for value, button in self.record_filter_chip_buttons.items():
            active = value == current
            button.base_bg = COLORS["selected"] if active else COLORS["bg_soft"]
            button.hover_bg = COLORS["selected"] if active else COLORS["hover"]
            button.pressed_bg = COLORS["selected"] if active else COLORS["selected"]
            button.base_fg = "white" if active else COLORS["text_secondary"]
            button.configure(
                bg=button.base_bg,
                fg=button.base_fg,
                activebackground=button.hover_bg,
                activeforeground=button.base_fg,
                highlightbackground=COLORS["accent_blue"] if active else COLORS["border"],
                highlightcolor=COLORS["accent_blue"] if active else COLORS["border"],
            )

    def _build_users_tab(self):
        tk.Label(
            self.users_tab,
            text="GESTION DE USUARIOS",
            font=("Consolas", 13, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["accent"],
        ).pack(anchor="w", padx=16, pady=(12, 4))

        frame = tk.Frame(self.users_tab, bg=COLORS["bg_dark"])
        frame.pack(fill="both", expand=True, padx=16, pady=8)

        left = tk.Frame(frame, bg=COLORS["bg_card"], highlightbackground=COLORS["border"], highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        columns = ("username", "rol", "activo", "email", "nombre_completo", "ultimo_acceso")
        self.user_table = ttk.Treeview(left, columns=columns, show="headings")
        widths = {
            "username": 120,
            "rol": 100,
            "activo": 80,
            "email": 210,
            "nombre_completo": 210,
            "ultimo_acceso": 160,
        }
        titles = {
            "username": "USUARIO",
            "rol": "ROL",
            "activo": "ACTIVO",
            "email": "EMAIL",
            "nombre_completo": "NOMBRE COMPLETO",
            "ultimo_acceso": "ULTIMO ACCESO",
        }
        for column in columns:
            self.user_table.heading(column, text=titles[column])
            self.user_table.column(column, width=widths[column], anchor="center")
        self.user_table.pack(fill="both", expand=True)
        self.user_table.bind("<<TreeviewSelect>>", self._load_selected_user)

        right = tk.Frame(
            frame,
            bg=COLORS["bg_card"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=16,
            pady=16,
            width=320,
        )
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(
            right,
            text="EDITAR / CREAR USUARIO",
            font=("Consolas", 10, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
        ).pack(anchor="w", pady=(0, 12))

        self.user_form = {}
        for label, key, field_type, options in [
            ("USUARIO", "username", "entry", None),
            ("NOMBRE COMPLETO", "nombre_completo", "entry", None),
            ("EMAIL", "email", "entry", None),
            ("ROL", "rol", "combo", VALID_ROLES),
            ("ACTIVO", "activo", "combo", ["True", "False"]),
            ("NUEVA CONTRASEÑA", "nueva_pass", "entry", None),
        ]:
            tk.Label(
                right,
                text=label,
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", pady=(4, 0))
            if field_type == "entry":
                widget = tk.Entry(
                    right,
                    font=("Consolas", 10),
                    bg=COLORS["bg_row"],
                    fg=COLORS["text_primary"],
                    insertbackground=COLORS["accent"],
                    relief="flat",
                    bd=4,
                )
                widget.pack(fill="x", ipady=4, pady=(2, 0))
            else:
                widget = ttk.Combobox(right, values=options, state="readonly", font=("Consolas", 10))
                widget.pack(fill="x", pady=(2, 0))
                widget.set(options[0])
            self.user_form[key] = widget

        separator(right).pack(fill="x", pady=10)

        SmartButton(
            right,
            "GUARDAR USUARIO",
            self._save_user,
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            height=2,
        ).pack(fill="x", pady=4)
        SmartButton(
            right,
            "LIMPIAR",
            self._clear_user_form,
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            height=2,
        ).pack(fill="x")

    def _build_footer(self):
        footer = tk.Frame(self.main, bg=COLORS["bg_panel"], height=34)
        footer.pack(fill="x", side="bottom")
        tk.Label(
            footer,
            text=f"{APP_COPYRIGHT} - {APP_NAME}",
            font=FONT_MINI,
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
        ).pack(side="right", padx=12)
        self.footer_status = tk.Label(
            footer,
            text=f"ROL ACTIVO: {self.role} | SESION: {self.username}",
            font=FONT_MINI,
            bg=COLORS["bg_panel"],
            fg=COLORS["accent"],
        )
        self.footer_status.pack(side="left", padx=12)
        self._update_session_status()

    def _update_session_status(self):
        if not hasattr(self, "footer_status"):
            return
        session = self.auth_service.get_session(self.session_id) if self.session_id else None
        if session:
            self.session_expires_at = session.get("expires_at", self.session_expires_at)
        display = self.session_expires_at.replace("T", " ") if self.session_expires_at else "N/D"
        color = COLORS["accent"]
        parsed = parse_iso_datetime(self.session_expires_at)
        if parsed and parsed <= datetime.now():
            color = COLORS["accent_red"]
        self.footer_status.config(
            text=f"ROL ACTIVO: {self.role} | SESION: {self.username} | EXPIRA: {display}",
            fg=color,
        )

    def _ensure_session_active(self, *, notify: bool = True) -> bool:
        if self.auth_service.is_session_active(self.session_id):
            return True
        if notify and not self.session_expired_notified:
            self.session_expired_notified = True
            messagebox.showwarning("SESION EXPIRADA", "La sesion ha expirado. Debes iniciar sesion de nuevo.")
        self.on_logout()
        return False

    def _set_status(self, text: str, color=None):
        self.header_status.config(text=text, fg=color or COLORS["text_secondary"])

    def _load_records(self):
        try:
            return self.record_service.list_records()
        except DataStoreError as error:
            messagebox.showerror("ERROR DE DATOS", str(error))
            return []

    def _refresh_all(self):
        if not self._ensure_session_active():
            return
        self._set_status("Datos actualizados correctamente", COLORS["success"])
        records = self._load_records()
        if self.is_admin:
            self._refresh_kpis(records)
            if self.admin_current_view == "dashboard" and self.chart_frames:
                self._refresh_dashboard(records)
        else:
            self.latest_records = list(records)
        self._refresh_record_table()
        if self.can_manage_users:
            self._refresh_user_table()

    def _refresh_kpis(self, records):
        kpis = self.analytics_service.build_kpis(records)
        self.latest_records = list(records)
        self.latest_kpis = dict(kpis)
        self.kpi_labels["total"].config(text=str(kpis["total"]))
        self.kpi_labels["valid"].config(text=str(kpis["valid"]))
        self.kpi_labels["errors"].config(text=str(kpis["errors"]))
        self.kpi_labels["today"].config(text=str(kpis["today"]))
        self.kpi_labels["residue_types"].config(text=str(kpis["residue_types"]))
        self.kpi_labels["efficiency_pct"].config(text=f"{kpis['efficiency_pct']:.1f}")
        self.kpi_labels["alerts"].config(text=str(kpis["alerts"]))
        self.kpi_labels["total_kg"].config(text=f"{kpis['total_kg']:.0f}")
        self._apply_kpi_tones(kpis)
        self._show_kpi_detail(self.selected_kpi_key)

    def _refresh_dashboard(self, records):
        if not self.chart_frames or self.insights_body is None:
            return
        charts = self.analytics_service.build_charts(records)
        alerts = self.analytics_service.calculate_alerts(records)
        if self.charts_enabled:
            self._draw_status_chart(charts["status"])
            self._draw_residue_chart(charts["residues"])
            self._draw_day_chart(charts["days"])
            self._draw_top_users_chart(charts["users"])
            self._draw_zone_chart(charts["zones"])
            self._draw_trend_chart(charts["trend_labels"], charts["trend_values"])
        else:
            for key in self.chart_frames:
                self._show_chart_placeholder(
                    key,
                    "Visualizacion no disponible",
                    "Instala matplotlib para habilitar las graficas del dashboard.",
                    show_action=False,
                )
            alerts = ["Las graficas estan desactivadas porque matplotlib no esta instalado."] + alerts

        if alerts:
            self._set_status(alerts[0], COLORS["warning"])
        self._render_insights(self._build_actionable_insights(records, alerts))

    def _apply_kpi_tones(self, kpis: dict):
        tones = {
            "total": COLORS["accent_blue"],
            "valid": COLORS["success"],
            "errors": COLORS["accent_red"] if kpis["errors"] else COLORS["text_primary"],
            "today": COLORS["accent_yellow"],
            "residue_types": COLORS["accent_purple"],
            "efficiency_pct": COLORS["success"] if kpis["efficiency_pct"] >= 80 else COLORS["warning"] if kpis["efficiency_pct"] >= 50 else COLORS["accent_red"],
            "alerts": COLORS["accent_red"] if kpis["alerts"] else COLORS["success"],
            "total_kg": COLORS["accent_orange"],
        }
        for key, color in tones.items():
            if key in self.kpi_labels:
                self.kpi_labels[key].config(fg=color)
            if key in self.kpi_icons:
                self.kpi_icons[key].config(fg=color)
            if key in self.kpi_cards:
                self.kpi_cards[key].configure(highlightbackground=COLORS["border"])
            if key in self.kpi_titles:
                self.kpi_titles[key].config(fg=COLORS["text_secondary"])
        self._highlight_selected_kpi()

    def _highlight_selected_kpi(self):
        for key, card in self.kpi_cards.items():
            active = key == self.selected_kpi_key
            shadow = self.kpi_shadows.get(key)
            top = self.kpi_top_rows.get(key)
            card.configure(
                highlightbackground=COLORS["accent"] if active else COLORS["border"],
                bg=COLORS["bg_soft"] if active else COLORS["bg_card"],
            )
            if shadow is not None:
                shadow.configure(bg=COLORS["accent_blue"] if active else COLORS["shadow"])
            if top is not None:
                top.configure(bg=COLORS["bg_soft"] if active else COLORS["bg_card"])
            if key in self.kpi_titles:
                self.kpi_titles[key].config(
                    bg=COLORS["bg_soft"] if active else COLORS["bg_card"],
                    fg=COLORS["text_primary"] if active else COLORS["text_secondary"],
                )
            if key in self.kpi_labels:
                self.kpi_labels[key].config(bg=COLORS["bg_soft"] if active else COLORS["bg_card"])
            if key in self.kpi_icons:
                self.kpi_icons[key].config(bg=COLORS["bg_dark"] if active else COLORS["bg_soft"])

    def _show_kpi_detail(self, key: str):
        self.selected_kpi_key = key
        if key in self.kpi_cards:
            self.kpi_cards[key].configure(bg=COLORS["hover"], highlightbackground=COLORS["accent_blue"])
            top = self.kpi_top_rows.get(key)
            if top is not None:
                top.configure(bg=COLORS["hover"])
        self.root.after(90, self._highlight_selected_kpi)

        kpis = self.latest_kpis or {}
        records = self.latest_records or []
        efficiency = self.analytics_service.calculate_efficiency(records)
        alerts = self.analytics_service.calculate_alerts(records)
        top_zones = self.analytics_service.top_zones(records)
        error_stats = self.analytics_service.error_analysis(records)
        residue_counts = self.analytics_service.build_charts(records)["residues"]

        details = {
            "total": (
                "Volumen total",
                "Vision general",
                [
                    f"Registros acumulados: {kpis.get('total', 0)}",
                    f"Entradas de hoy: {kpis.get('today', 0)}",
                    f"Tipos detectados: {kpis.get('residue_types', 0)}",
                ],
            ),
            "valid": (
                "Calidad operativa",
                "Registros correctos",
                [
                    f"Registros validos: {kpis.get('valid', 0)}",
                    "Mantener este indicador alto reduce retrabajos.",
                    "Usa este KPI como referencia de calidad diaria.",
                ],
            ),
            "errors": (
                "Foco de correccion",
                "Requiere revision",
                [
                    f"Registros con error: {kpis.get('errors', 0)}",
                    f"Tasa de error: {efficiency.get('error_rate_pct', 0.0):.1f}%",
                    "Revisa los ultimos registros si esta tendencia crece.",
                ],
            ),
            "today": (
                "Actividad del dia",
                "Ritmo actual",
                [
                    f"Entradas registradas hoy: {kpis.get('today', 0)}",
                    "Util para comparar la carga operativa del dia.",
                    "Aumenta cuando el equipo esta capturando actividad reciente.",
                ],
            ),
            "residue_types": (
                "Diversidad de residuos",
                "Cobertura",
                [
                    f"Tipos activos: {kpis.get('residue_types', 0)}",
                    f"Residuo principal: {next(iter(residue_counts.keys()), 'N/D')}",
                    "Te ayuda a entender variedad y demanda de manejo.",
                ],
            ),
            "efficiency_pct": (
                "Eficiencia del sistema",
                "Salud operativa",
                [
                    f"Eficiencia actual: {kpis.get('efficiency_pct', 0.0):.1f}%",
                    f"Tasa de error: {efficiency.get('error_rate_pct', 0.0):.1f}%",
                    "Sube cuando la captura es consistente y baja cuando hay retrabajo.",
                ],
            ),
            "alerts": (
                "Alertas inteligentes",
                "Riesgos",
                alerts[:3] if alerts else ["Todo funcionando correctamente.", "Sin alertas criticas.", "No necesitas acciones urgentes ahora."],
            ),
            "total_kg": (
                "Peso acumulado",
                "Impacto",
                [
                    f"Peso total registrado: {kpis.get('total_kg', 0.0):.0f} kg",
                    f"Zona lider: {top_zones[0]['zona']} ({top_zones[0]['total_kg']:.1f} kg)" if top_zones else "Aun no hay zonas activas.",
                    f"Usuario con mas incidencias: {error_stats[0]['usuario']}" if error_stats else "Aun no hay usuarios suficientes para comparar.",
                ],
            ),
        }
        title, badge, lines = details.get(
            key,
            ("Detalle del KPI", "Resumen", ["Selecciona un KPI para ver su desglose."]),
        )
        self.kpi_detail_title.config(text=title)
        self.kpi_detail_badge.config(text=badge)
        self.kpi_detail_body.config(text="\n".join(f"- {line}" for line in lines))

    def _build_actionable_insights(self, records, alerts: list[str]) -> list[tuple[str, str, str, str]]:
        if len(records) < 5:
            return [
                ("+", "Aun no tienes datos", "Crea tu primer registro para comenzar.", "neutral"),
                ("i", "Necesitas mas contexto", "Registra al menos 5 entradas para activar las metricas automaticas.", "neutral"),
                ("*", "Siguiente paso", "Usa el menu lateral para abrir Nuevo registro y empezar la operacion.", "accent"),
            ]

        efficiency = self.analytics_service.calculate_efficiency(records)
        zones = self.analytics_service.top_zones(records)
        heavy = self.analytics_service.heavy_contributors(records)
        insights: list[tuple[str, str, str, str]] = []

        if alerts:
            insights.append(("\u26a0", "Atencion operativa", alerts[0] + " Revisa los ultimos registros.", "warning"))
        else:
            insights.append(("\u2714", "Operación estable", "Todo funcionando correctamente. Sin alertas críticas.", "success"))

        insights.append(
            (
                "\u26a1",
                "Eficiencia actual",
                f"La eficiencia es {efficiency['efficiency_pct']:.1f}%. Prioriza mantener registros validos y consistentes.",
                "accent",
            )
        )

        if zones:
            insights.append(
                (
                    "\u25b2",
                    "Zona con mayor actividad",
                    f"{zones[0]['zona']} lidera con {zones[0]['total_kg']:.1f} kg. Usa esta zona como referencia operativa.",
                    "neutral",
                )
            )
        if heavy:
            insights.append(
                (
                    "\u25cf",
                    "Contribuyente destacado",
                    f"{heavy[0]['usuario']} acumula {heavy[0]['total_kg']:.1f} kg. Revisa si necesita seguimiento preferente.",
                    "neutral",
                )
            )
        return insights[:4]

    def _render_insights(self, insight_cards: list[tuple[str, str, str, str]]):
        for widget in self.insights_body.winfo_children():
            widget.destroy()

        tone_colors = {
            "success": COLORS["success"],
            "warning": COLORS["warning"],
            "accent": COLORS["accent_blue"],
            "neutral": COLORS["text_secondary"],
        }
        for index, (icon, title, detail, tone) in enumerate(insight_cards):
            shadow, card = self._create_elevated_card(self.insights_body, bg_key="bg_soft")
            shadow.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
            self.insights_body.grid_columnconfigure(index % 2, weight=1)

            accent_rail = tk.Frame(card, bg=tone_colors.get(tone, COLORS["text_secondary"]), width=5)
            accent_rail.pack(side="left", fill="y")

            body_wrap = tk.Frame(card, bg=COLORS["bg_soft"])
            body_wrap.pack(side="left", fill="both", expand=True, padx=12, pady=10)

            icon_label = tk.Label(
                body_wrap,
                text=icon,
                font=("Consolas", 12, "bold"),
                bg=COLORS["bg_dark"],
                fg=tone_colors.get(tone, COLORS["text_secondary"]),
                width=3,
                pady=4,
            )
            icon_label.pack(side="left", padx=(0, 10))

            body = tk.Frame(body_wrap, bg=COLORS["bg_soft"])
            body.pack(side="left", fill="x", expand=True)
            tk.Label(
                body,
                text=title,
                font=("Consolas", 9, "bold"),
                bg=COLORS["bg_soft"],
                fg=COLORS["text_primary"],
                anchor="w",
                justify="left",
            ).pack(fill="x")
            tk.Label(
                body,
                text=detail,
                font=("Consolas", 8),
                bg=COLORS["bg_soft"],
                fg=COLORS["text_secondary"],
                anchor="w",
                justify="left",
                wraplength=320,
            ).pack(fill="x", pady=(4, 0))

    def _clear_chart_frame(self, key: str):
        for widget in self.chart_frames[key].winfo_children():
            widget.destroy()

    def _make_figure(self, width=3.8, height=2.6):
        if plt is None:
            raise RuntimeError("matplotlib no esta disponible")
        fig, axis = plt.subplots(figsize=(width, height), dpi=90)
        fig.patch.set_facecolor(COLORS["bg_card"])
        axis.set_facecolor(COLORS["bg_card"])
        return fig, axis

    def _embed_chart(self, fig, key: str):
        if FigureCanvasTkAgg is None:
            return
        canvas = FigureCanvasTkAgg(fig, master=self.chart_frames[key])
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self.chart_canvases.append(canvas)
        plt.close(fig)

    def _show_chart_placeholder(self, key: str, title: str, message: str, *, show_action: bool = False):
        self._clear_chart_frame(key)
        wrapper = tk.Frame(self.chart_frames[key], bg=COLORS["bg_card"])
        wrapper.pack(fill="both", expand=True, padx=8, pady=12)
        tk.Label(
            wrapper,
            text="\u25cc",
            justify="center",
            font=("Consolas", 28, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["border"],
        ).pack(pady=(8, 8))
        preview = tk.Canvas(
            wrapper,
            bg=COLORS["bg_card"],
            height=86,
            highlightthickness=0,
        )
        preview.pack(fill="x")
        preview.create_polygon(22, 62, 56, 48, 92, 54, 128, 30, 172, 38, 172, 64, 22, 64, fill=COLORS["bg_soft"], outline="")
        preview.create_line(22, 52, 56, 42, 92, 48, 128, 24, 172, 32, fill=COLORS["border"], width=2, smooth=True)
        preview.create_line(22, 64, 182, 64, fill=COLORS["border"])
        preview.create_line(22, 18, 22, 64, fill=COLORS["border"])
        tk.Label(
            wrapper,
            text=title,
            justify="center",
            font=("Consolas", 11, "bold"),
            bg=COLORS["bg_card"],
            fg=COLORS["text_primary"],
        ).pack(pady=(8, 4))
        tk.Label(
            wrapper,
            text=message,
            justify="center",
            font=("Consolas", 8),
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
        ).pack()
        if show_action:
            tk.Label(
                wrapper,
                text="Usa el menu lateral para ir a Nuevo registro.",
                justify="center",
                font=("Consolas", 8),
                bg=COLORS["bg_card"],
                fg=COLORS["text_secondary"],
            ).pack(pady=(12, 0))

    def _draw_status_chart(self, status_data):
        self._clear_chart_frame("status")
        valid = status_data.get("VALIDO", 0)
        error = status_data.get("ERROR", 0)
        total = valid + error
        if total == 0:
            self._show_chart_placeholder(
                "status",
                "Aun no tienes datos",
                "Crea tu primer registro para comenzar.",
            )
            return
        fig, axis = self._make_figure()
        axis.pie(
            [valid, error],
            labels=["VALIDO", "ERROR"],
            autopct="%1.0f%%",
            colors=[COLORS["accent"], COLORS["accent_red"]],
            wedgeprops=dict(width=0.45),
            startangle=90,
            textprops={"color": "white", "fontfamily": "Consolas", "fontsize": 8},
        )
        axis.text(0, 0, f"{total}\nREG.", ha="center", va="center", color=COLORS["text_primary"])
        fig.tight_layout()
        self._embed_chart(fig, "status")

    def _draw_residue_chart(self, residue_data):
        self._clear_chart_frame("residues")
        if not residue_data:
            self._show_chart_placeholder(
                "residues",
                "Aun no tienes datos",
                "Crea tu primer registro para comenzar.",
            )
            return
        fig, axis = self._make_figure()
        labels = list(residue_data.keys())
        values = list(residue_data.values())
        colors = [MATERIAL_COLORS.get(label, COLORS["accent_blue"]) for label in labels]
        bars = axis.bar(labels, values, color=colors, width=0.55, edgecolor=COLORS["bg_dark"])
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                str(int(bar.get_height())),
                ha="center",
                color="white",
                fontsize=8,
                fontfamily="Consolas",
            )
        axis.tick_params(axis="x", labelsize=7)
        axis.tick_params(axis="y", labelsize=7)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        fig.tight_layout()
        self._embed_chart(fig, "residues")

    def _draw_day_chart(self, day_data):
        self._clear_chart_frame("days")
        ordered = ["LUN", "MAR", "MIE", "JUE", "VIE", "SAB", "DOM"]
        values = [day_data.get(day, 0) for day in ordered]
        if not any(values):
            self._show_chart_placeholder(
                "days",
                "Aun no tienes datos",
                "Tus registros por dia apareceran aqui cuando empieces a operar.",
            )
            return
        fig, axis = self._make_figure()
        axis.plot(ordered, values, color=COLORS["accent"], linewidth=2, marker="o", markersize=6)
        axis.fill_between(ordered, values, alpha=0.15, color=COLORS["accent"])
        axis.tick_params(axis="x", labelsize=7)
        axis.tick_params(axis="y", labelsize=7)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        fig.tight_layout()
        self._embed_chart(fig, "days")

    def _draw_top_users_chart(self, user_data):
        self._clear_chart_frame("users")
        if not user_data:
            self._show_chart_placeholder(
                "users",
                "Aun no tienes datos",
                "Crea tu primer registro para comenzar.",
            )
            return
        fig, axis = self._make_figure()
        top = user_data.most_common(6)
        labels = [item[0] for item in top]
        values = [item[1] for item in top]
        colors = plt.cm.get_cmap("cool")([index / max(len(top) - 1, 1) for index in range(len(top))])
        bars = axis.barh(labels, values, color=colors, edgecolor=COLORS["bg_dark"])
        for bar in bars:
            axis.text(
                bar.get_width() + 0.05,
                bar.get_y() + bar.get_height() / 2,
                str(int(bar.get_width())),
                va="center",
                color="white",
                fontsize=8,
                fontfamily="Consolas",
            )
        axis.tick_params(axis="x", labelsize=7)
        axis.tick_params(axis="y", labelsize=7)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        fig.tight_layout()
        self._embed_chart(fig, "users")

    def _draw_zone_chart(self, zone_data):
        self._clear_chart_frame("zones")
        if not zone_data:
            self._show_chart_placeholder(
                "zones",
                "Aun no tienes datos",
                "Crea tu primer registro para comenzar.",
            )
            return
        fig, axis = self._make_figure(width=5, height=2.6)
        labels = list(zone_data.keys())
        values = list(zone_data.values())
        colors = [
            COLORS["accent_blue"],
            COLORS["accent_yellow"],
            COLORS["accent"],
            COLORS["accent_red"],
            COLORS["accent_purple"],
            COLORS["accent_orange"],
        ][: len(labels)]
        bars = axis.bar(labels, values, color=colors, edgecolor=COLORS["bg_dark"])
        for bar in bars:
            axis.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.05,
                f"{bar.get_height():.1f}",
                ha="center",
                color="white",
                fontsize=8,
                fontfamily="Consolas",
            )
        axis.tick_params(axis="x", labelsize=7, rotation=20)
        axis.tick_params(axis="y", labelsize=7)
        axis.set_ylabel("KG", color=COLORS["text_secondary"], fontsize=7, fontfamily="Consolas")
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        fig.tight_layout()
        self._embed_chart(fig, "zones")

    def _draw_trend_chart(self, labels, values):
        self._clear_chart_frame("trend")
        if not any(values):
            self._show_chart_placeholder(
                "trend",
                "Aun no tienes datos",
                "Crea tu primer registro para comenzar.",
            )
            return
        fig, axis = self._make_figure(width=5, height=2.6)
        axis.plot(labels, values, color=COLORS["accent_blue"], linewidth=2, marker="s", markersize=5)
        axis.fill_between(labels, values, alpha=0.10, color=COLORS["accent_blue"])
        axis.tick_params(axis="x", labelsize=7, rotation=30)
        axis.tick_params(axis="y", labelsize=7)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.set_ylabel("REGISTROS", color=COLORS["text_secondary"], fontsize=7, fontfamily="Consolas")
        fig.tight_layout()
        self._embed_chart(fig, "trend")

    def _collect_form_data(self):
        return {
            "usuario": self.form_widgets["usuario"].get(),
            "registrado": self.form_widgets["registrado"].get(),
            "residuo": self.form_widgets["residuo"].get(),
            "zona": self.form_widgets["zona"].get(),
            "direccion": self.form_widgets["direccion"].get(),
            "dia": self.form_widgets["dia"].get(),
            "peso_kg": self.form_widgets["peso_kg"].get(),
            "notas": self.form_widgets["notas"].get(),
        }

    def _submit_operator_record(self):
        if self.operator_submit_in_progress:
            return
        if self.selected_index is not None:
            self._update_record()
            return
        self._save_record()

    def _set_operator_validation_message(self, text: str = "", color: str | None = None):
        if self.operator_validation_label is not None and self.operator_validation_label.winfo_exists():
            self.operator_validation_label.config(text=text, fg=color or COLORS["warning"])

    def _handle_operator_primary_action(self):
        if self.operator_current_view != "form":
            self.render_operator_form_view()
            return
        self._submit_operator_record()

    def _sync_operator_primary_button(self):
        if self.operator_primary_button is None or not self.operator_primary_button.winfo_exists():
            return
        self.button_save = self.operator_primary_button
        if self.operator_current_view == "form":
            self.operator_primary_button.configure(command=self._handle_operator_primary_action)
        else:
            self.operator_primary_button.configure(command=self._handle_operator_primary_action)
            self.operator_primary_button.config(text="Nuevo registro")
            self.operator_edit_mode = False
            self.operator_loaded_record_snapshot = None
            self._apply_operator_primary_style(False)

    def _apply_operator_primary_style(self, edit_mode: bool):
        if not self.is_operator:
            return
        bg = COLORS["accent_blue"] if edit_mode else COLORS["accent"]
        hover = COLORS["selected"] if edit_mode else COLORS["accent_dim"]
        fg = "white" if edit_mode else COLORS["bg_dark"]
        for button in [*self.operator_primary_buttons, getattr(self, "button_save", None)]:
            if button is None:
                continue
            button.base_bg = bg
            button.hover_bg = hover
            button.pressed_bg = hover
            button.base_fg = fg
            button.configure(bg=bg, fg=fg, activebackground=hover, activeforeground=fg)

    def _set_operator_edit_mode(self, enabled: bool):
        self.operator_edit_mode = enabled
        if self.operator_edit_label is not None and self.operator_edit_label.winfo_exists():
            self.operator_edit_label.config(text="Editando registro" if enabled else "")
        if hasattr(self, "button_save"):
            self.button_save.config(text="ACTUALIZAR REGISTRO" if enabled else "CREAR REGISTRO")
        for button in self.operator_primary_buttons:
            button.config(text="Actualizar registro" if enabled else "Nuevo registro")
        self._apply_operator_primary_style(enabled)
        if enabled:
            self.operator_loaded_record_snapshot = self._snapshot_form_data()
        else:
            self.operator_loaded_record_snapshot = None

    def _set_operator_loading_state(self, enabled: bool, text: str = "Guardando..."):
        if not self.is_operator or not hasattr(self, "button_save"):
            return
        self.operator_submit_in_progress = enabled
        controls = [self.button_save, self.button_clear, *self.operator_primary_buttons]
        if enabled:
            for button in controls:
                button.config(text=text)
                button.lock()
            return
        self.button_save.unlock()
        self.button_clear.unlock()
        self.button_clear.config(text="CANCELAR")
        for button in self.operator_primary_buttons:
            button.unlock()
        self._set_operator_edit_mode(self.selected_index is not None)

    def _snapshot_form_data(self) -> dict[str, str]:
        return {key: str(value).strip() for key, value in self._collect_form_data().items()}

    def _is_operator_form_dirty(self) -> bool:
        if not self.is_operator or not self.operator_edit_mode or not self.operator_loaded_record_snapshot:
            return False
        return self._snapshot_form_data() != self.operator_loaded_record_snapshot

    def _restore_selected_record_row(self):
        if self.selected_index is None or not hasattr(self, "record_table"):
            return
        expected_tag = str(self.selected_index)
        for item_id, tags in self.record_table_base_tags.items():
            if tags and tags[0] == expected_tag:
                self.record_table.selection_set(item_id)
                self.record_table.focus(item_id)
                return

    def _confirm_operator_discard_changes(self) -> bool:
        if not self._is_operator_form_dirty():
            return True
        discard = messagebox.askyesno(
            "Cambios sin guardar",
            "Tienes cambios sin guardar. ¿Deseas continuar sin guardarlos?",
        )
        if not discard:
            self._restore_selected_record_row()
        return discard

    def _focus_operator_form(self):
        if "usuario" not in self.form_widgets:
            return
        self.root.update_idletasks()
        self.form_widgets["usuario"].focus_set()
        self.root.focus_force()

    def _clear_form_errors(self):
        self.form_error_fields.clear()
        for widget in self.form_widgets.values():
            if isinstance(widget, ttk.Combobox):
                widget.configure(style="TCombobox")
            else:
                widget.configure(
                    highlightbackground=COLORS["border"],
                    highlightcolor=COLORS["border"],
                    bg=COLORS["bg_row"],
                )

    def _extract_invalid_fields(self, errors: list[str]) -> list[str]:
        mapping = {
            "usuario": ("usuario",),
            "registrado": ("registrado",),
            "residuo": ("residuo", "tipo de residuo"),
            "zona": ("zona",),
            "direccion": ("direccion", "direcci"),
            "dia": ("dia", "recoleccion"),
            "peso_kg": ("peso", "kg"),
            "notas": ("nota",),
        }
        invalid_fields = []
        for error in errors:
            lowered = error.lower()
            for field_name, keywords in mapping.items():
                if any(keyword in lowered for keyword in keywords) and field_name not in invalid_fields:
                    invalid_fields.append(field_name)
        return invalid_fields

    def _highlight_invalid_fields(self, errors: list[str]):
        self._clear_form_errors()
        invalid_fields = self._extract_invalid_fields(errors)
        if not invalid_fields:
            return
        self.form_error_fields.update(invalid_fields)
        for field_name in invalid_fields:
            widget = self.form_widgets.get(field_name)
            if widget is None:
                continue
            if isinstance(widget, ttk.Combobox):
                widget.configure(style="Invalid.TCombobox")
            else:
                widget.configure(
                    highlightbackground=COLORS["accent_red"],
                    highlightcolor=COLORS["accent_red"],
                    bg=COLORS["bg_soft"],
                )
        first_widget = self.form_widgets.get(invalid_fields[0])
        if first_widget is not None:
            first_widget.focus_set()

    def _cancel_record_edit(self):
        if self.is_operator and not self._confirm_operator_discard_changes():
            return
        self._clear_form()
        if self.is_operator:
            self.render_operator_table_view()
        self._set_status("Edición cancelada", COLORS["accent_blue"])

    def _save_record(self):
        if not self._ensure_session_active():
            return
        self._clear_form_errors()
        self._set_operator_validation_message("")
        self._set_operator_loading_state(True, "Guardando...")
        self.root.update_idletasks()
        try:
            result = self.record_service.create_record(
                self._collect_form_data(),
                self.username,
                session_id=self.session_id,
            )
        except Exception:
            self._set_operator_validation_message("No se pudo guardar el registro", COLORS["accent_red"])
            messagebox.showerror("ERROR", "No se pudo guardar el registro")
            return
        finally:
            self._set_operator_loading_state(False)
        if not result.ok:
            self._highlight_invalid_fields(result.errors or [])
            self._set_operator_validation_message(
                "Completa los campos obligatorios" if result.errors else "No se pudo guardar el registro",
                COLORS["warning"] if result.errors else COLORS["accent_red"],
            )
            messagebox.showerror("ERROR", "No se pudo guardar el registro")
            return
        self._refresh_records_after_mutation()
        self._clear_form()
        self._set_operator_validation_message("")
        self._queue_feedback("✔ Registro creado correctamente", "success")
        if self.is_operator:
            self.render_operator_table_view()
        elif self.is_admin:
            self.render_admin_records()
        self._set_status("Registro creado correctamente", COLORS["success"])

    def _update_record(self):
        if not self._ensure_session_active():
            return
        if self.selected_index is None:
            messagebox.showwarning("AVISO", "Seleccione un registro primero.")
            return
        if self.is_operator and not self._record_belongs_to_current_user(self._get_record_by_index(self.selected_index)):
            messagebox.showerror("DENEGADO", "Solo puedes editar registros creados por ti.")
            return
        self._clear_form_errors()
        self._set_operator_validation_message("")
        self._set_operator_loading_state(True, "Guardando...")
        self.root.update_idletasks()
        try:
            result = self.record_service.update_record(
                self.selected_index,
                self._collect_form_data(),
                self.username,
                session_id=self.session_id,
            )
        except Exception:
            self._set_operator_validation_message("No se pudo guardar el registro", COLORS["accent_red"])
            messagebox.showerror("ERROR", "No se pudo guardar el registro")
            return
        finally:
            self._set_operator_loading_state(False)
        if not result.ok:
            self._highlight_invalid_fields(result.errors or [])
            self._set_operator_validation_message(
                "Completa los campos obligatorios" if result.errors else "No se pudo guardar el registro",
                COLORS["warning"] if result.errors else COLORS["accent_red"],
            )
            messagebox.showerror("ERROR", "No se pudo guardar el registro")
            return
        self._refresh_records_after_mutation()
        self._clear_form()
        self._set_operator_validation_message("")
        self._queue_feedback("✔ Registro actualizado correctamente", "success")
        if self.is_operator:
            self.render_operator_table_view()
        elif self.is_admin:
            self.render_admin_records()
        self._set_status("Registro actualizado correctamente", COLORS["accent_yellow"])

    def _delete_record(self, *, index: int | None = None):
        if not self._ensure_session_active():
            return
        target_index = self.selected_index if index is None else index
        if target_index is None:
            messagebox.showwarning("AVISO", "Seleccione un registro primero.")
            return
        record = self._get_record_by_index(target_index)
        if record is None:
            messagebox.showerror("ERROR", "El registro seleccionado ya no existe.")
            return
        if not self.can_delete_records:
            if not self.is_operator or not self._record_belongs_to_current_user(record):
                messagebox.showerror("DENEGADO", "Solo puedes eliminar registros creados por ti.")
                return
        if not messagebox.askyesno("CONFIRMAR", "¿Seguro que deseas eliminar este registro? Esta acción no se puede deshacer."):
            return
        result = self.record_service.delete_record(
            target_index,
            self.username,
            session_id=self.session_id,
        )
        if not result.ok:
            messagebox.showerror("ERROR", result.message)
            return
        self._refresh_records_after_mutation()
        self._clear_form()
        self._show_inline_feedback("✔ Registro eliminado correctamente", tone="success")
        self._set_status("Registro eliminado correctamente", COLORS["accent_red"])

    def _set_form_state(self, state):
        for widget in self.form_widgets.values():
            if isinstance(widget, ttk.Combobox):
                widget.configure(state="readonly" if state == "normal" else "disabled")
            else:
                widget.configure(state=state)

    def _clear_form(self):
        self._clear_form_errors()
        self._set_operator_validation_message("")
        for key, widget in self.form_widgets.items():
            if isinstance(widget, ttk.Combobox):
                widget.set("SI" if key == "registrado" else "")
            else:
                widget.delete(0, tk.END)
        self.selected_index = None
        if self.is_operator:
            self._set_operator_edit_mode(False)
            self._focus_operator_form()

    def _open_record_form(self):
        self._open_new_record()

    def _clear_form_and_open_records(self):
        self._open_records()

    def _get_filtered_records(self) -> list[tuple[int, dict]]:
        if self.record_table_mode == "operator":
            records = self.latest_records or self._load_records()
            current_username = str(self.current_user.username).strip().upper()
            query = self.search_entry.get().strip().upper() if self.search_entry is not None else ""
            filtered_records = []
            for index, record in enumerate(records):
                if str(record.get("creado_por", "")).strip().upper() != current_username:
                    continue
                search_blob = " ".join(
                    [
                        record.get("residuo", ""),
                        record.get("zona", ""),
                        record.get("direccion", ""),
                        record.get("dia", ""),
                        record.get("estado", ""),
                    ]
                ).upper()
                if query and query not in search_blob:
                    continue
                filtered_records.append((index, record))
            return filtered_records
        return self.record_service.filter_records(
            query=self.search_entry.get() if self.search_entry is not None else "",
            status=self.filter_status.get() if self.filter_status is not None else "TODOS",
            residue=self.filter_residue.get() if self.filter_residue is not None else "TODOS",
            zone=self.filter_zone.get() if self.filter_zone is not None else "TODAS",
        )

    def _get_record_by_index(self, index: int | None) -> dict | None:
        records = self.latest_records or self._load_records()
        if index is None or index < 0 or index >= len(records):
            return None
        return records[index]

    def _record_belongs_to_current_user(self, record: dict | None) -> bool:
        if record is None:
            return False
        return str(record.get("creado_por", "")).strip().upper() == str(self.current_user.username).strip().upper()

    def _load_record_into_form(self, index: int) -> bool:
        if self.is_operator and "usuario" not in self.form_widgets:
            self.render_operator_form_view()
        if self.is_admin and "usuario" not in self.form_widgets:
            self.render_admin_new_record()
        record = self._get_record_by_index(index)
        if record is None:
            return False
        if self.is_operator and not self._record_belongs_to_current_user(record):
            messagebox.showerror("DENEGADO", "Solo puedes editar registros creados por ti.")
            return False
        if self.is_operator and self.selected_index is not None and index != self.selected_index:
            if not self._confirm_operator_discard_changes():
                return False
        self._clear_form_errors()
        self._set_operator_validation_message("")
        self.selected_index = index
        for key, widget in self.form_widgets.items():
            value = record.get(key, "")
            if isinstance(widget, ttk.Combobox):
                widget.set(value)
            else:
                widget.delete(0, tk.END)
                widget.insert(0, value)
        if self.is_operator:
            self._set_operator_edit_mode(True)
            self._focus_operator_form()
        return True

    def _refresh_records_after_mutation(self):
        if self.record_table_mode == "operator":
            self.latest_records = list(self._load_records())
            self._refresh_record_table()
            return
        self._refresh_all()

    def _refresh_record_table(self):
        if not hasattr(self, "record_table") or self.record_table is None:
            return
        self._clear_record_row_hover()
        self.record_table_base_tags.clear()
        for item in self.record_table.get_children():
            self.record_table.delete(item)

        filtered = self._get_filtered_records()
        display_records = filtered
        if self.record_table_mode == "operator":
            display_records = list(reversed(filtered[-12:]))
        for row_number, (index, record) in enumerate(display_records):
            state_tag = "valid" if record.get("estado") == "VALIDO" else "error"
            stripe_tag = "row_even" if row_number % 2 == 0 else "row_odd"
            row_values = (
                (
                    record.get("residuo", ""),
                    record.get("zona", "CENTRO"),
                    truncate_text(record.get("direccion", ""), 42),
                    record.get("dia", ""),
                    record.get("peso_kg", ""),
                    record.get("estado", ""),
                    "EDITAR   ELIMINAR",
                )
                if self.record_table_mode == "operator"
                else (
                    record.get("usuario", ""),
                    record.get("registrado", ""),
                    record.get("residuo", ""),
                    record.get("zona", "CENTRO"),
                    truncate_text(record.get("direccion", ""), 32),
                    record.get("dia", ""),
                    record.get("peso_kg", ""),
                    record.get("estado", ""),
                    record.get("fecha", ""),
                    record.get("creado_por", "-"),
                    truncate_text(record.get("notas", ""), 32),
                )
            )
            item_id = self.record_table.insert(
                "",
                "end",
                values=row_values,
                tags=(str(index), stripe_tag, state_tag),
            )
            self.record_table_base_tags[item_id] = (str(index), stripe_tag, state_tag)

        if self.record_table_mode == "operator":
            own_total = len(filtered)
            if self.operator_record_empty_state is not None:
                if display_records:
                    self.operator_record_empty_state.pack_forget()
                else:
                    self.operator_record_empty_state.pack(fill="x", padx=16, pady=(0, 4), before=self.record_table)
            self.record_status.config(text=f"MOSTRANDO {len(display_records)} DE {own_total} REGISTROS PERSONALES")
        else:
            total_records = len(self.record_service.list_records())
            self.record_status.config(text=f"MOSTRANDO {len(filtered)} DE {total_records} REGISTROS")
            self._sync_residue_filter_chips()

    def _on_record_table_motion(self, event):
        row_id = self.record_table.identify_row(event.y)
        if not row_id:
            self._clear_record_row_hover()
            return
        if row_id == self.hovered_record_item:
            return
        self._clear_record_row_hover()
        base_tags = self.record_table_base_tags.get(row_id)
        if not base_tags:
            return
        self.record_table.item(row_id, tags=base_tags + ("hover_row",))
        self.hovered_record_item = row_id

    def _clear_record_row_hover(self, _=None):
        if self.hovered_record_item and self.hovered_record_item in self.record_table_base_tags:
            self.record_table.item(
                self.hovered_record_item,
                tags=self.record_table_base_tags[self.hovered_record_item],
            )
        self.hovered_record_item = None

    def _handle_record_table_click(self, event):
        if self.record_table_mode != "operator" or not self.record_table_action_column:
            return None
        row_id = self.record_table.identify_row(event.y)
        column_id = self.record_table.identify_column(event.x)
        if not row_id or column_id != self.record_table_action_column:
            return None

        self.record_table.selection_set(row_id)
        self.record_table.focus(row_id)
        index = self._get_index_from_item(row_id)
        if index is None:
            return "break"

        bbox = self.record_table.bbox(row_id, column_id)
        if not bbox:
            self._load_record_into_form(index)
            return "break"

        cell_x, _cell_y, cell_width, _cell_height = bbox
        relative_x = max(event.x - cell_x, 0)
        if relative_x <= cell_width / 2:
            self._load_record_into_form(index)
        else:
            self._delete_record(index=index)
        return "break"

    def _get_index_from_item(self, item_id: str) -> int | None:
        try:
            return int(self.record_table.item(item_id, "tags")[0])
        except (TypeError, ValueError, IndexError):
            return None

    def _load_selected_record(self, _=None):
        selection = self.record_table.selection()
        if not selection:
            return
        item_id = selection[0]
        index = self._get_index_from_item(item_id)
        if index is None:
            self.selected_index = None
            return
        if self.is_operator and self.operator_current_view == "records":
            self.selected_index = index
            return
        self._load_record_into_form(index)

    def _reset_filters(self):
        if self.search_entry is not None:
            self.search_entry.delete(0, tk.END)
        if self.filter_status is not None:
            self.filter_status.set("TODOS")
        if self.filter_residue is not None:
            self.filter_residue.set("TODOS")
            self._sync_residue_filter_chips()
        if self.filter_zone is not None:
            self.filter_zone.set("TODAS")
        self._refresh_record_table()
        self._set_status("Filtros restablecidos", COLORS["accent_blue"])

    def _export_csv(self):
        if not self._ensure_session_active():
            return
        filtered_records = [record for _, record in self._get_filtered_records()]
        if not filtered_records:
            messagebox.showwarning("SIN DATOS", "No hay registros para exportar con los filtros actuales.")
            return
        target = filedialog.asksaveasfilename(
            title="Guardar CSV",
            defaultextension=".csv",
            initialfile=self.record_service.default_export_path("csv").name,
            initialdir=str(self.record_service.default_export_path("csv").parent),
            filetypes=[("CSV", "*.csv")],
        )
        if not target:
            return
        result = self.record_service.export_csv(
            target,
            filtered_records,
            self.username,
            session_id=self.session_id,
        )
        if result.ok:
            self._set_status(result.message, COLORS["accent_purple"])
            messagebox.showinfo("EXPORTACION EXITOSA", f"{result.message}\nRegistros exportados: {result.count}")
        else:
            messagebox.showerror("ERROR", result.message)

    def _export_json(self):
        if not self._ensure_session_active():
            return
        filtered_records = [record for _, record in self._get_filtered_records()]
        if not filtered_records:
            messagebox.showwarning("SIN DATOS", "No hay registros para exportar con los filtros actuales.")
            return
        target = filedialog.asksaveasfilename(
            title="Guardar JSON",
            defaultextension=".json",
            initialfile=self.record_service.default_export_path("json").name,
            initialdir=str(self.record_service.default_export_path("json").parent),
            filetypes=[("JSON", "*.json")],
        )
        if not target:
            return
        result = self.record_service.export_json(
            target,
            filtered_records,
            self.username,
            session_id=self.session_id,
        )
        if result.ok:
            self._set_status(result.message, COLORS["accent_blue"])
            messagebox.showinfo("EXPORTACION EXITOSA", f"{result.message}\nRegistros exportados: {result.count}")
        else:
            messagebox.showerror("ERROR", result.message)

    def _import_csv(self):
        if not self._ensure_session_active():
            return
        if not self.can_edit_records:
            messagebox.showerror("DENEGADO", "Tu rol es de solo lectura.")
            return
        source = filedialog.askopenfilename(
            title="Selecciona un archivo para importar",
            filetypes=[("CSV", "*.csv"), ("JSON", "*.json")],
        )
        if not source:
            return
        if source.lower().endswith(".json"):
            result = self.record_service.import_json(source, self.username, session_id=self.session_id)
        else:
            result = self.record_service.import_csv(source, self.username, session_id=self.session_id)
        self._refresh_all()
        if result.errors:
            preview = "\n".join(result.errors[:8])
            messagebox.showwarning("IMPORTACION CON OBSERVACIONES", f"{result.message}\n\n{preview}")
        elif result.ok:
            messagebox.showinfo("IMPORTACION EXITOSA", result.message)
        else:
            messagebox.showerror("ERROR", result.message)

    def _refresh_user_table(self):
        if not self._ensure_session_active(notify=False):
            return
        if self.user_table is None or not self.user_table.winfo_exists():
            return
        for item in self.user_table.get_children():
            self.user_table.delete(item)
        users = self.user_service.list_users()
        for username, data in users.items():
            self.user_table.insert(
                "",
                "end",
                values=(
                    username,
                    data.get("rol", ""),
                    "SI" if data.get("activo") else "NO",
                    data.get("email", ""),
                    data.get("nombre_completo", ""),
                    data.get("ultimo_acceso", ""),
                ),
            )

    def _load_selected_user(self, _=None):
        if self.user_table is None or not self.user_table.winfo_exists() or not self.user_form:
            return
        selection = self.user_table.selection()
        if not selection:
            return
        values = self.user_table.item(selection[0], "values")
        if not values:
            return
        username = values[0]
        user = self.user_service.list_users().get(username)
        if not user:
            return
        self.user_form["username"].delete(0, tk.END)
        self.user_form["username"].insert(0, username)
        self.user_form["nombre_completo"].delete(0, tk.END)
        self.user_form["nombre_completo"].insert(0, user.get("nombre_completo", ""))
        self.user_form["email"].delete(0, tk.END)
        self.user_form["email"].insert(0, user.get("email", ""))
        self.user_form["rol"].set(user.get("rol", "OPERADOR"))
        self.user_form["activo"].set(str(user.get("activo", True)))
        self.user_form["nueva_pass"].delete(0, tk.END)

    def _save_user(self):
        if not self._ensure_session_active():
            return
        if not self.user_form:
            return
        payload = {
            "username": self.user_form["username"].get(),
            "nombre_completo": self.user_form["nombre_completo"].get(),
            "email": self.user_form["email"].get(),
            "rol": self.user_form["rol"].get(),
            "activo": self.user_form["activo"].get() == "True",
            "nueva_pass": self.user_form["nueva_pass"].get(),
        }
        result = self.user_service.save_user(
            payload,
            self.username,
            actor_role=self.role,
            session_id=self.session_id,
        )
        if not result.ok:
            messagebox.showerror("ERROR", "\n".join(result.errors or [result.message]))
            return
        self._refresh_user_table()
        self._clear_user_form()
        messagebox.showinfo("EXITO", result.message)

    def _clear_user_form(self):
        if not self.user_form:
            return
        for key, widget in self.user_form.items():
            if isinstance(widget, ttk.Combobox):
                widget.set("OPERADOR" if key == "rol" else "True" if key == "activo" else "")
            else:
                widget.delete(0, tk.END)

    def _open_audit_window(self):
        if not self._ensure_session_active():
            return
        logs = self.system_service.list_logs()
        window = tk.Toplevel(self.root)
        window.title(f"{APP_COPYRIGHT} - {APP_NAME}")
        window.geometry("1150x560")
        window.configure(bg=COLORS["bg_dark"])

        tk.Label(
            window,
            text="AUDITORIA DEL SISTEMA",
            font=("Consolas", 15, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["accent"],
        ).pack(pady=12)

        filters = tk.Frame(window, bg=COLORS["bg_dark"])
        filters.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            filters,
            text="FILTRAR:",
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        ).pack(side="left")

        search = tk.Entry(
            filters,
            width=28,
            font=("Consolas", 10),
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            relief="flat",
            bd=4,
        )
        search.pack(side="left", padx=6, ipady=4)

        columns = ("level", "usuario", "accion", "detalle", "fecha", "hora")
        table = ttk.Treeview(window, columns=columns, show="headings")
        widths = {"level": 100, "usuario": 140, "accion": 170, "detalle": 380, "fecha": 120, "hora": 120}
        for column in columns:
            table.heading(column, text=column.upper())
            table.column(column, width=widths[column], anchor="center")
        table.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        total_label = tk.Label(
            window,
            text="",
            font=("Consolas", 8),
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
        )
        total_label.pack(pady=4)

        def populate(filter_text=""):
            for item in table.get_children():
                table.delete(item)
            filtered_logs = self.system_service.list_logs(filter_text)
            for log in filtered_logs:
                table.insert(
                    "",
                    "end",
                    values=(
                        log.get("level", "INFO"),
                        log.get("usuario", ""),
                        log.get("accion", ""),
                        log.get("detalle", ""),
                        log.get("fecha", ""),
                        log.get("hora", ""),
                    ),
                )
            total_label.config(text=f"TOTAL MOSTRADO: {len(filtered_logs)} | TOTAL GENERAL: {len(logs)}")

        search.bind("<KeyRelease>", lambda _: populate(search.get().strip()))
        populate()

    def _create_backup(self):
        if not self._ensure_session_active():
            return
        if not self.can_manage_users:
            messagebox.showerror("DENEGADO", "Solo el administrador puede generar backups.")
            return
        backup_dir = self.system_service.create_backup(self.username, session_id=self.session_id)
        self._set_status(f"Backup creado en {backup_dir.name}", COLORS["success"])
        messagebox.showinfo("BACKUP OK", f"Copia creada en:\n{backup_dir}")

    def _confirm_uninstall_application(self):
        if not self._ensure_session_active():
            return
        if not self.can_manage_users:
            messagebox.showerror("DENEGADO", "Solo el administrador puede desinstalar la aplicacion.")
            return

        try:
            self.system_service.get_uninstaller_path()
        except DataStoreError as error:
            messagebox.showerror("ERROR", str(error))
            return

        if not messagebox.askyesno(
            "Confirmar desinstalacion",
            "Se abrira el desinstalador del sistema.\nDesea continuar?",
            icon="warning",
            parent=self.root,
        ):
            return

        try:
            self.system_service.uninstall_application(
                self.username,
                session_id=self.session_id,
            )
        except DataStoreError as error:
            messagebox.showerror("ERROR", str(error))
            return

        self.auth_service.register_exit(self.session_id, self.username)
        self.root.withdraw()
        self.root.after(700, self.root.destroy)

    def _logout(self):
        if not messagebox.askyesno("CERRAR SESION", "Deseas cerrar la sesion actual?"):
            return
        self.auth_service.close_session(self.session_id, self.username)
        self.on_logout()

    def _exit_application(self):
        self.auth_service.register_exit(self.session_id, self.username)
        self.root.destroy()
