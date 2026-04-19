from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from app.config import APP_COPYRIGHT, APP_NAME, COLORS
from app.core.utils import center_window
from app.ui.widgets import SmartButton, Tooltip


class LoginView:
    def __init__(self, root, auth_service, user_service, on_login_success):
        self.root = root
        self.auth_service = auth_service
        self.user_service = user_service
        self.on_login_success = on_login_success
        self.show_password = False

        self.root.title(f"{APP_COPYRIGHT} - {APP_NAME}")
        self.root.configure(bg=COLORS["bg_dark"])
        self.root.resizable(False, False)
        center_window(self.root, 460, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=COLORS["bg_dark"])
        outer.pack(fill="both", expand=True, padx=28, pady=28)

        card = tk.Frame(
            outer,
            bg=COLORS["bg_panel"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=26,
            pady=26,
        )
        card.pack(fill="both", expand=True)

        tk.Label(
            card,
            text="INICIAR SESIÓN",
            font=("Consolas", 13, "bold"),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_primary"],
        ).pack(anchor="w", pady=(0, 18))

        self.entry_user = self._build_entry(card, "USUARIO", False)
        self.entry_password = self._build_entry(card, "CONTRASEÑA", True)

        tools = tk.Frame(card, bg=COLORS["bg_panel"])
        tools.pack(fill="x", pady=(6, 16))

        self.button_show = SmartButton(
            tools,
            "MOSTRAR",
            self._toggle_password,
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            hover=COLORS["selected"],
            width=12,
            height=1,
        )
        self.button_show.pack(side="left")
        Tooltip(self.button_show, "Ver u ocultar la contraseña")

        self.entry_password.bind("<Return>", lambda _: self._login())

        SmartButton(
            card,
            "ACCEDER →",
            self._login,
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            hover=COLORS["accent_dim"],
            height=2,
        ).pack(fill="x", pady=(4, 12))

        SmartButton(
            card,
            "REGISTRAR USUARIO",
            self._open_register_window,
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            hover=COLORS["selected"],
            height=2,
        ).pack(fill="x")

    def _build_entry(self, parent, title: str, is_password: bool):
        tk.Label(
            parent,
            text=title,
            font=("Consolas", 9, "bold"),
            bg=COLORS["bg_panel"],
            fg=COLORS["accent"],
        ).pack(anchor="w")
        entry = tk.Entry(
            parent,
            show="*" if is_password else "",
            font=("Consolas", 11),
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            insertbackground=COLORS["accent"],
            relief="flat",
            bd=8,
        )
        entry.pack(fill="x", pady=(4, 12), ipady=6)
        return entry

    def _toggle_password(self):
        self.show_password = not self.show_password
        self.entry_password.config(show="" if self.show_password else "*")
        self.button_show.config(text="OCULTAR" if self.show_password else "MOSTRAR")

    def _login(self):
        result = self.auth_service.authenticate(self.entry_user.get(), self.entry_password.get())
        if result.ok:
            self.on_login_success(
                result.username,
                result.role,
                result.session_id,
                result.expires_at,
            )
            return

        title = "BLOQUEADO" if result.blocked_seconds else "ACCESO DENEGADO"
        messagebox.showerror(title, result.message)

    def _open_register_window(self):
        window = tk.Toplevel(self.root)
        window.title(f"{APP_COPYRIGHT} - {APP_NAME}")
        window.configure(bg=COLORS["bg_dark"])
        window.resizable(False, False)
        center_window(window, 440, 540)

        card = tk.Frame(
            window,
            bg=COLORS["bg_panel"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=20,
            pady=20,
        )
        card.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(
            card,
            text="REGISTRAR USUARIO",
            font=("Consolas", 12, "bold"),
            bg=COLORS["bg_panel"],
            fg=COLORS["accent"],
        ).pack(anchor="w", pady=(0, 12))

        fields: dict[str, tk.Entry] = {}
        specs = [
            ("USUARIO", "username", False),
            ("NOMBRE COMPLETO", "nombre_completo", False),
            ("EMAIL", "email", False),
            ("CONTRASEÑA", "password", True),
            ("CONFIRMAR CONTRASEÑA", "confirm_password", True),
        ]
        for label, key, masked in specs:
            tk.Label(
                card,
                text=label,
                font=("Consolas", 8, "bold"),
                bg=COLORS["bg_panel"],
                fg=COLORS["text_secondary"],
            ).pack(anchor="w", pady=(4, 0))
            entry = tk.Entry(
                card,
                show="*" if masked else "",
                font=("Consolas", 10),
                bg=COLORS["bg_row"],
                fg=COLORS["text_primary"],
                insertbackground=COLORS["accent"],
                relief="flat",
                bd=4,
            )
            entry.pack(fill="x", ipady=4, pady=(2, 0))
            fields[key] = entry

        status = tk.Label(
            card,
            text="Los usuarios creados desde aquí entran como OPERADOR.",
            font=("Consolas", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
            justify="left",
            wraplength=340,
        )
        status.pack(anchor="w", pady=(12, 10))

        feedback = tk.Label(
            card,
            text="",
            font=("Consolas", 8),
            bg=COLORS["bg_panel"],
            fg=COLORS["text_secondary"],
            justify="left",
            wraplength=360,
        )
        feedback.pack(fill="x", pady=(0, 10))

        def submit_registration():
            payload = {key: entry.get() for key, entry in fields.items()}
            result = self.user_service.register_user(payload)
            if not result.ok:
                error_message = "\n".join(result.errors or [result.message])
                feedback.config(text=error_message, fg=COLORS["accent_red"])
                messagebox.showerror("ERROR", error_message, parent=window)
                return

            feedback.config(text=result.message, fg=COLORS["success"])
            messagebox.showinfo("ÉXITO", result.message, parent=window)
            for entry in fields.values():
                entry.delete(0, tk.END)
            window.destroy()

        button_frame = tk.Frame(card, bg=COLORS["bg_panel"])
        button_frame.pack(fill="x", pady=(4, 0))

        SmartButton(
            button_frame,
            "REGISTRAR",
            submit_registration,
            bg=COLORS["accent"],
            fg=COLORS["bg_dark"],
            height=2,
        ).pack(fill="x", pady=(0, 8))

        SmartButton(
            button_frame,
            "CERRAR",
            window.destroy,
            bg=COLORS["bg_row"],
            fg=COLORS["text_primary"],
            height=2,
        ).pack(fill="x")
