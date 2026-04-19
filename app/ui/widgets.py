from __future__ import annotations

import tkinter as tk

from app.config import COLORS, FONT_BUTTON, FONT_MINI


def separator(parent, bg=None, height: int = 1):
    frame = tk.Frame(parent, bg=bg or COLORS["border"], height=height)
    frame.pack_propagate(False)
    return frame


class Tooltip:
    def __init__(self, widget, text: str):
        self.widget = widget
        self.text = text
        self.tip = None
        self.widget.bind("<Enter>", self.show)
        self.widget.bind("<Leave>", self.hide)

    def show(self, _=None):
        if self.tip:
            return
        x_pos = self.widget.winfo_rootx() + 14
        y_pos = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x_pos}+{y_pos}")
        self.tip.configure(bg="#1a2540")
        tk.Label(
            self.tip,
            text=self.text,
            font=FONT_MINI,
            bg="#1a2540",
            fg=COLORS["text_primary"],
            padx=8,
            pady=4,
        ).pack()

    def hide(self, _=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None


class SmartButton(tk.Button):
    def __init__(self, parent, text, command, bg, fg="white", hover=None, **kwargs):
        self.pressed_bg = kwargs.pop("pressed", hover or COLORS["selected"])
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            bd=0,
            relief="flat",
            cursor="hand2",
            font=kwargs.pop("font", FONT_BUTTON),
            activebackground=self.pressed_bg,
            activeforeground=fg,
            highlightthickness=1,
            highlightbackground=kwargs.pop("highlightbackground", COLORS["border"]),
            highlightcolor=kwargs.pop("highlightcolor", COLORS["border"]),
            **kwargs,
        )
        self.base_bg = bg
        self.base_fg = fg
        self.hover_bg = hover or COLORS["hover"]
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _=None):
        if str(self["state"]) != "disabled":
            self.configure(bg=self.hover_bg)

    def _on_leave(self, _=None):
        if str(self["state"]) != "disabled":
            self.configure(bg=self.base_bg)

    def _on_press(self, _=None):
        if str(self["state"]) != "disabled":
            self.configure(bg=self.pressed_bg)

    def _on_release(self, event=None):
        if str(self["state"]) == "disabled":
            return
        if event is None:
            self.configure(bg=self.base_bg)
            return
        inside_widget = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self.configure(bg=self.hover_bg if inside_widget else self.base_bg)

    def lock(self):
        self.configure(
            state="disabled",
            bg=COLORS["border"],
            fg=COLORS["text_secondary"],
            cursor="arrow",
        )

    def unlock(self):
        self.configure(
            state="normal",
            bg=self.base_bg,
            fg=self.base_fg,
            cursor="hand2",
        )
