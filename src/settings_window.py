import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Optional

from .settings_manager import read_secrets, save_secrets, validate_secrets


class SettingsWindow(tk.Toplevel):
    """Modal settings window for Spotify credentials."""

    def __init__(self, master: tk.Misc, on_saved: Optional[Callable[[Dict[str, str]], None]] = None, theme: Dict[str, str] = None):
        super().__init__(master)
        self.title("Settings")
        self.transient(master)
        self.resizable(False, False)
        self.grab_set()  # modal
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # Theme defaults (fallbacks if not provided)
        self.theme = theme or {
            "bg": "#121212",
            "panel": "#181818",
            "label_fg": "#B3B3B3",
            "entry_bg": "#282828",
            "entry_fg": "#FFFFFF",
            "accent": "#1DB954",
            "accent_hover": "#1ED760",
            "accent_active": "#1AA34A",
            "button_fg": "#FFFFFF",
            "button_bg": "#282828",
            "button_fg_alt": "#121212",
            "button_bg_alt": "#B3B3B3",
        }

        self.configure(bg=self.theme["bg"]) 
        self.on_saved = on_saved

        current = read_secrets()

        container = tk.Frame(self, bg=self.theme["panel"], padx=20, pady=20)
        container.pack(fill=tk.BOTH, expand=True)

        # Fields
        self.vars: Dict[str, tk.StringVar] = {
            "client_id": tk.StringVar(value=current.get("client_id", "")),
            "client_secret": tk.StringVar(value=current.get("client_secret", "")),
            "redirect_uri": tk.StringVar(value=current.get("redirect_uri", "http://127.0.0.1:8080")),
            "sp_dc_cookie": tk.StringVar(value=current.get("sp_dc_cookie", "")),
        }

        row = 0
        for key, label in [
            ("client_id", "Client ID"),
            ("client_secret", "Client Secret"),
            ("redirect_uri", "Redirect URI"),
            ("sp_dc_cookie", "sp_dc Cookie"),
        ]:
            lbl = tk.Label(container, text=label, bg=self.theme["panel"], fg=self.theme["label_fg"]) 
            lbl.grid(row=row, column=0, sticky="w", pady=(0, 6))

            show = "*" if key == "client_secret" else None
            entry = tk.Entry(container, textvariable=self.vars[key], show=show, bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
            entry.grid(row=row, column=1, sticky="ew", pady=(0, 6))
            row += 1

        container.grid_columnconfigure(1, weight=1)

        # Buttons
        buttons = tk.Frame(container, bg=self.theme["panel"]) 
        buttons.grid(row=row, column=0, columnspan=2, sticky="e", pady=(12, 0))

        cancel_btn = tk.Button(buttons, text="Cancel", command=self._on_cancel, bg=self.theme["button_bg"], fg=self.theme["button_fg"], relief=tk.FLAT, padx=16, pady=8, cursor="hand2")
        cancel_btn.pack(side=tk.RIGHT, padx=(0, 8))

        save_btn = tk.Button(buttons, text="Save", command=self._on_save, bg=self.theme["accent"], fg=self.theme["button_fg"], activebackground=self.theme["accent_active"], relief=tk.FLAT, padx=16, pady=8, cursor="hand2")
        save_btn.pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _collect_values(self) -> Dict[str, str]:
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _on_save(self) -> None:
        values = self._collect_values()
        ok, missing = validate_secrets(values)
        if not ok:
            messagebox.showerror("Missing fields", f"Please fill: {', '.join(missing)}")
            return
        try:
            save_secrets(values)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
            return
        if self.on_saved:
            self.on_saved(values)
        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self.grab_release()
        self.destroy()
