import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Dict, Optional

from .settings_manager import read_secrets, save_secrets, validate_secrets
from .translation_settings import (
    read_translation_settings,
    save_translation_settings,
    read_models_config,
    save_models_config,
    DEFAULT_PROMPT,
    DEFAULT_MODEL_PARAMS,
)
from .translation_clients import fetch_openrouter_models, format_model_display
from .font_manager import get_available_fonts, get_default_chinese_font

def get_selected_font():
    """Get the currently selected font from settings."""
    settings = read_translation_settings()
    return settings.get("selected_font", get_default_chinese_font())


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
        tsettings = read_translation_settings()
        models_config = read_models_config()

        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Spotify Tab
        tab_spotify = tk.Frame(notebook, bg=self.theme["panel"], padx=20, pady=20)
        notebook.add(tab_spotify, text="Spotify")

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
            lbl = tk.Label(tab_spotify, text=label, bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')) 
            lbl.grid(row=row, column=0, sticky="w", pady=(0, 6))

            show = "*" if key == "client_secret" else None
            entry = tk.Entry(tab_spotify, textvariable=self.vars[key], show=show, bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
            entry.grid(row=row, column=1, sticky="ew", pady=(0, 6))
            row += 1

        tab_spotify.grid_columnconfigure(1, weight=1)

        # Translation Tab
        tab_translation = tk.Frame(notebook, bg=self.theme["panel"], padx=20, pady=20)
        notebook.add(tab_translation, text="Translation")

        # Provider selection
        provider_var = tk.StringVar(value=tsettings.get("provider", "Google Translate"))
        tk.Label(tab_translation, text="Provider", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=0, column=0, sticky="w")
        provider_combo = ttk.Combobox(tab_translation, textvariable=provider_var, values=["Google Translate", "OpenRouter"], state="readonly")
        provider_combo.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        # Target language
        target_lang_var = tk.StringVar(value=tsettings.get("target_language", "en"))
        tk.Label(tab_translation, text="Target Language (e.g., en)", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=1, column=0, sticky="w")
        target_lang_entry = tk.Entry(tab_translation, textvariable=target_lang_var, bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
        target_lang_entry.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        # OpenRouter API key
        openrouter_key_var = tk.StringVar(value=current.get("openrouter_api_key", ""))
        openrouter_key_label = tk.Label(tab_translation, text="OpenRouter API Key", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal'))
        openrouter_key_label.grid(row=2, column=0, sticky="w")
        openrouter_key_entry = tk.Entry(tab_translation, textvariable=openrouter_key_var, show="*", bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
        openrouter_key_entry.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        # Model dropdown (dynamic via OpenRouter API)
        model_display_var = tk.StringVar(value=tsettings.get("selected_model", "openrouter/auto"))
        model_label = tk.Label(tab_translation, text="OpenRouter Model", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal'))
        model_label.grid(row=3, column=0, sticky="w")
        model_combo = ttk.Combobox(tab_translation, textvariable=model_display_var, values=[model_display_var.get()], state="normal")
        model_combo.grid(row=3, column=1, sticky="ew", pady=(0, 6))
        # Refresh models button
        refresh_models_btn = tk.Button(
            tab_translation,
            text="Refresh Models",
            bg=self.theme["button_bg"],
            fg=self.theme["button_fg"],
            relief=tk.FLAT,
            padx=10,
            pady=6,
            cursor="hand2",
            font=(get_selected_font(), 10, 'normal'),
        )
        refresh_models_btn.grid(row=3, column=2, sticky="w")

        # JSON body editor for selected model
        body_label = tk.Label(tab_translation, text="Model JSON Body", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal'))
        body_label.grid(row=4, column=0, sticky="nw")
        body_text = tk.Text(tab_translation, height=10, bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
        body_text.grid(row=4, column=1, sticky="nsew", pady=(0, 6))

        # Mapping from display label -> model id
        self._model_display_to_id: Dict[str, str] = {}
        self._models_cache = []  # raw fetched model list
        self._all_model_displays = []  # full display list for typeahead
        self._filtered_model_displays = []

        # Persistent dropdown popup for typeahead suggestions
        self._model_popup: Optional[tk.Toplevel] = None
        self._model_listbox: Optional[tk.Listbox] = None

        def _hide_model_popup():
            try:
                if self._model_popup is not None:
                    self._model_popup.withdraw()
            except Exception:
                pass

        def _ensure_model_popup() -> bool:
            if self._model_popup is not None and self._model_popup.winfo_exists():
                return True
            try:
                popup = tk.Toplevel(self)
                popup.overrideredirect(True)
                popup.configure(bg=self.theme["panel"]) 
                try:
                    popup.attributes("-topmost", True)
                except Exception:
                    pass

                listbox = tk.Listbox(
                    popup,
                    bg=self.theme["entry_bg"],
                    fg=self.theme["entry_fg"],
                    selectbackground=self.theme["accent"],
                    activestyle="none",
                    highlightthickness=0,
                    relief=tk.FLAT,
                )
                listbox.pack(fill=tk.BOTH, expand=True)

                def on_click_select(_):
                    try:
                        sel = listbox.curselection()
                        if sel:
                            value = listbox.get(sel[0])
                            model_display_var.set(value)
                            load_model_body()
                    except Exception:
                        pass
                    _hide_model_popup()
                    try:
                        model_combo.focus_set()
                    except Exception:
                        pass

                listbox.bind("<ButtonRelease-1>", on_click_select)

                self._model_popup = popup
                self._model_listbox = listbox
                return True
            except Exception:
                return False

        def _place_model_popup():
            if self._model_popup is None:
                return
            try:
                x = model_combo.winfo_rootx()
                y = model_combo.winfo_rooty() + model_combo.winfo_height()
                width = model_combo.winfo_width()
                # Fixed height; listbox scrolls implicitly
                height = 200
                self._model_popup.geometry(f"{width}x{height}+{x}+{y}")
                self._model_popup.deiconify()
            except Exception:
                pass

        def _update_model_popup(values: list):
            if not values:
                _hide_model_popup()
                return
            if not _ensure_model_popup():
                return
            try:
                lb = self._model_listbox
                if lb is None:
                    return
                lb.delete(0, tk.END)
                for v in values:
                    lb.insert(tk.END, v)
                # Select best visible match
                try:
                    current_text = model_combo.get()
                    idx = 0
                    low = current_text.lower()
                    for i, v in enumerate(values):
                        if v.lower().startswith(low):
                            idx = i
                            break
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(idx)
                    lb.activate(idx)
                    lb.see(idx)
                except Exception:
                    pass
            except Exception:
                pass
            _place_model_popup()

        def _current_model_id_from_display() -> str:
            display = model_display_var.get()
            return self._model_display_to_id.get(display, display)

        def load_model_body(*_):
            import json
            model_id = _current_model_id_from_display()
            body = models_config.get(model_id, DEFAULT_MODEL_PARAMS)
            try:
                body_text.delete("1.0", tk.END)
                body_text.insert("1.0", json.dumps(body, ensure_ascii=False, indent=2))
            except Exception:
                body_text.delete("1.0", tk.END)
                body_text.insert("1.0", "{}")

        model_combo.bind("<<ComboboxSelected>>", load_model_body)
        load_model_body()

        def _populate_models_async(show_messages: bool = True) -> None:
            import threading

            def worker():
                api_key = openrouter_key_var.get().strip()
                items = fetch_openrouter_models(api_key)

                def on_ui():
                    # If failed or missing key
                    if not items:
                        if show_messages:
                            try:
                                messagebox.showinfo("OpenRouter", "Could not fetch models. Check your API key or try again later.")
                            except Exception:
                                pass
                        # Fallback to a minimal default option
                        fallback_vals = ["openrouter/auto"]
                        model_combo.configure(values=fallback_vals)
                        model_display_var.set("openrouter/auto")
                        load_model_body()
                        return

                    self._models_cache = items
                    # Build display list and mapping
                    display_values = []
                    mapping: Dict[str, str] = {}
                    for m in items:
                        label = format_model_display(m)
                        display_values.append(label)
                        mapping[label] = m.get("id", "")
                    self._model_display_to_id = mapping
                    self._all_model_displays = display_values[:]

                    # Try to preserve previous selection by id
                    prev_id = tsettings.get("selected_model", "openrouter/auto")
                    # Find display for prev_id
                    selected_display = None
                    for disp, mid in mapping.items():
                        if mid == prev_id:
                            selected_display = disp
                            break

                    model_combo.configure(values=display_values)
                    if selected_display:
                        model_display_var.set(selected_display)
                    else:
                        # Default to first item or previous raw value
                        if display_values:
                            model_display_var.set(display_values[0])

                    # After updating selection, load body
                    load_model_body()

                try:
                    self.after(0, on_ui)
                except Exception:
                    pass

            threading.Thread(target=worker, daemon=True).start()

        def on_refresh_models():
            _populate_models_async(show_messages=True)

        refresh_models_btn.configure(command=on_refresh_models)


        def on_model_keyrelease(event):
            # Filter the dropdown values based on current typed text
            # Ignore navigation keys
            if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
                return
            typed = model_combo.get()
            if not typed:
                self._filtered_model_displays = self._all_model_displays[:]
                model_combo.configure(values=self._all_model_displays or model_combo.cget("values"))
                _update_model_popup(self._filtered_model_displays)
                return
            low = typed.lower()
            filtered = [d for d in (self._all_model_displays or []) if low in d.lower()]
            self._filtered_model_displays = filtered[:]
            model_combo.configure(values=filtered or self._all_model_displays or model_combo.cget("values"))
            _update_model_popup(self._filtered_model_displays)

        model_combo.bind("<KeyRelease>", on_model_keyrelease)

        def _navigate_listbox(delta: int):
            lb = self._model_listbox
            if lb is None or not lb.winfo_ismapped():
                _update_model_popup(self._filtered_model_displays or self._all_model_displays)
                return
            try:
                sel = lb.curselection()
                if sel:
                    idx = sel[0]
                else:
                    idx = 0
                idx = max(0, min(lb.size() - 1, idx + delta))
                lb.selection_clear(0, tk.END)
                lb.selection_set(idx)
                lb.activate(idx)
                lb.see(idx)
            except Exception:
                pass

        def _accept_selection():
            lb = self._model_listbox
            if lb is None or not lb.winfo_ismapped():
                return
            try:
                sel = lb.curselection()
                if sel:
                    value = lb.get(sel[0])
                    model_display_var.set(value)
                    load_model_body()
                _hide_model_popup()
            except Exception:
                pass

        def _cancel_popup():
            _hide_model_popup()

        def on_model_keypress_nav(event):
            if event.keysym == "Down":
                _navigate_listbox(1)
                return "break"
            if event.keysym == "Up":
                _navigate_listbox(-1)
                return "break"
            if event.keysym in ("Return",):
                _accept_selection()
                return "break"
            if event.keysym in ("Escape",):
                _cancel_popup()
                return "break"

        model_combo.bind("<KeyPress>", on_model_keypress_nav, add=True)

        def _commit_best_match():
            # If current text isn't exactly one of the display labels, commit the first filtered match
            current = model_display_var.get()
            if current in self._model_display_to_id:
                return True
            candidate_list = self._filtered_model_displays or self._all_model_displays
            if candidate_list:
                model_display_var.set(candidate_list[0])
                try:
                    load_model_body()
                except Exception:
                    pass
                return True
            return False

        # Return is handled by the popup navigation handler; avoid duplicate binding

        def on_provider_changed(*_):
            toggle_openrouter_settings()
            if provider_var.get() == "OpenRouter":
                _populate_models_async(show_messages=False)

        provider_combo.bind("<<ComboboxSelected>>", on_provider_changed)
        # Initial fetch if provider is OpenRouter and API key is present
        if provider_var.get() == "OpenRouter" and (openrouter_key_var.get().strip()):
            _populate_models_async(show_messages=False)

        # Global prompt editor
        prompt_label = tk.Label(tab_translation, text="Global Prompt", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal'))
        prompt_label.grid(row=5, column=0, sticky="nw")
        prompt_text = tk.Text(tab_translation, height=8, bg=self.theme["entry_bg"], fg=self.theme["entry_fg"], insertbackground=self.theme["entry_fg"], relief=tk.FLAT)
        prompt_text.grid(row=5, column=1, sticky="nsew")
        prompt_text.insert("1.0", tsettings.get("global_prompt", DEFAULT_PROMPT))

        def toggle_openrouter_settings():
            """Toggle visibility of OpenRouter-specific settings based on provider selection."""
            is_openrouter = provider_var.get() == "OpenRouter"

            # Control visibility of OpenRouter widgets
            widgets_to_toggle = [
                openrouter_key_label, openrouter_key_entry,
                model_label, model_combo, refresh_models_btn,
                body_label, body_text,
                prompt_label, prompt_text
            ]

            for widget in widgets_to_toggle:
                if is_openrouter:
                    widget.grid()  # Show the widget
                else:
                    widget.grid_remove()  # Hide the widget

        # Set initial visibility state (after all widgets are created)
        toggle_openrouter_settings()

        # Save buttons row for translation tab
        def on_save_translation():
            # Save secrets with API key
            secrets_to_save = {
                "client_id": self.vars["client_id"].get(),
                "client_secret": self.vars["client_secret"].get(),
                "redirect_uri": self.vars["redirect_uri"].get(),
                "sp_dc_cookie": self.vars["sp_dc_cookie"].get(),
                "openrouter_api_key": openrouter_key_var.get().strip(),
            }
            try:
                save_secrets(secrets_to_save)
            except Exception:
                pass

            # Save translation settings
            selected_display = model_display_var.get()
            selected_model_id = self._model_display_to_id.get(selected_display, selected_display)
            save_translation_settings({
                "provider": provider_var.get(),
                "selected_model": selected_model_id,
                "target_language": target_lang_var.get().strip() or "en",
                "global_prompt": prompt_text.get("1.0", tk.END).strip() or DEFAULT_PROMPT,
                "selected_font": font_var.get(),
                "font_size": font_size_var.get(),
                "font_bold": font_bold_var.get(),
                "floating_font": floating_font_var.get(),
                "floating_font_size": floating_font_size_var.get(),
                "floating_font_bold": floating_font_bold_var.get(),
            })

            # Save model body
            import json
            try:
                raw = body_text.get("1.0", tk.END)
                parsed = json.loads(raw) if raw else {}
                if not isinstance(parsed, dict) or len(parsed) == 0:
                    parsed = DEFAULT_MODEL_PARAMS
                models_config[selected_model_id] = parsed
                save_models_config(models_config)
            except Exception:
                # ignore invalid JSON silently here; the app will keep last valid
                # but if invalid, try to persist defaults to ensure runnable
                try:
                    models_config[selected_model_id] = DEFAULT_MODEL_PARAMS
                    save_models_config(models_config)
                except Exception:
                    pass

            if self.on_saved:
                self.on_saved(secrets_to_save)

        tab_translation.grid_columnconfigure(1, weight=1)
        tab_translation.grid_columnconfigure(2, weight=0)
        tab_translation.grid_rowconfigure(4, weight=1)
        tab_translation.grid_rowconfigure(5, weight=1)

        # Font Selection Tab
        tab_font = tk.Frame(notebook, bg=self.theme["panel"], padx=20, pady=20)
        notebook.add(tab_font, text="Font")

        # Main Window Fonts header
        main_font_label = tk.Label(tab_font, text="Main Window Fonts", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 12, 'bold'))
        main_font_label.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 5))

        # Font selection dropdown
        font_var = tk.StringVar(value=tsettings.get("selected_font", get_default_chinese_font()))
        tk.Label(tab_font, text="Font", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=1, column=0, sticky="w")

        # Get available fonts (Chinese and English)
        available_fonts = get_available_fonts()
        font_combo = ttk.Combobox(tab_font, textvariable=font_var, values=available_fonts, state="readonly")
        font_combo.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        # Font size slider
        font_size_var = tk.IntVar(value=tsettings.get("font_size", 12))
        tk.Label(tab_font, text="Font Size", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=2, column=0, sticky="w")

        size_frame = tk.Frame(tab_font, bg=self.theme["panel"])
        size_frame.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        size_scale = tk.Scale(
            size_frame,
            from_=8,
            to=24,
            orient=tk.HORIZONTAL,
            variable=font_size_var,
            bg=self.theme["panel"],
            fg=self.theme["label_fg"],
            troughcolor=self.theme["entry_bg"],
            highlightbackground=self.theme["panel"]
        )
        size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        size_value_label = tk.Label(
            size_frame,
            textvariable=font_size_var,
            bg=self.theme["panel"],
            fg=self.theme["label_fg"],
            font=(get_selected_font(), 10, 'normal'),
            width=3
        )
        size_value_label.pack(side=tk.RIGHT, padx=(10, 0))

        # Font bold toggle
        font_bold_var = tk.BooleanVar(value=tsettings.get("font_bold", True))
        tk.Label(tab_font, text="Bold Text", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=3, column=0, sticky="w")

        bold_check = tk.Checkbutton(
            tab_font,
            variable=font_bold_var,
            bg=self.theme["panel"],
            activebackground=self.theme["panel"],
            selectcolor=self.theme["panel"]
        )
        bold_check.grid(row=3, column=1, sticky="w", pady=(0, 6))

        # Font preview
        preview_frame = tk.Frame(tab_font, bg=self.theme["panel"])
        preview_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        tk.Label(preview_frame, text="Font Preview:", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).pack(anchor="w")

        preview_text = tk.Label(
            preview_frame,
            text="When I was young, I listened to the radio, waiting for my favorite songs. Now I have Spotify, and I can hear any song I want anytime. Music brings back memories of the past.\n\n当我年轻的时候，我听着收音机，等着我最喜欢的歌曲。现在我有了Spotify，我可以随时听到任何我想听的歌。音乐能让我回忆起过去的时光。",
            bg=self.theme["entry_bg"],
            fg=self.theme["entry_fg"],
            font=(font_var.get(), font_size_var.get(), 'bold' if font_bold_var.get() else 'normal'),
            relief=tk.FLAT,
            padx=10,
            pady=10,
            wraplength=700,
            justify='left'
        )
        preview_text.pack(fill=tk.X, pady=(5, 0))

        # Update preview when any setting changes
        def update_preview(*_):
            weight = 'bold' if font_bold_var.get() else 'normal'
            preview_text.config(font=(font_var.get(), font_size_var.get(), weight))

        font_var.trace_add("write", update_preview)
        font_size_var.trace_add("write", update_preview)
        font_bold_var.trace_add("write", update_preview)

        # Separator
        separator = ttk.Separator(tab_font, orient='horizontal')
        separator.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(20, 10))

        # Floating Window Font Settings
        floating_label = tk.Label(tab_font, text="Floating Window Fonts", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 12, 'bold'))
        floating_label.grid(row=6, column=0, columnspan=2, sticky='w', pady=(10, 5))

        # Floating window font selection
        floating_font_var = tk.StringVar(value=tsettings.get("floating_font", get_default_chinese_font()))
        tk.Label(tab_font, text="Font", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=7, column=0, sticky="w")

        floating_font_combo = ttk.Combobox(tab_font, textvariable=floating_font_var, values=available_fonts, state="readonly")
        floating_font_combo.grid(row=7, column=1, sticky="ew", pady=(0, 6))

        # Floating window font size slider
        floating_font_size_var = tk.IntVar(value=tsettings.get("floating_font_size", 12))
        tk.Label(tab_font, text="Font Size", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=8, column=0, sticky="w")

        floating_size_frame = tk.Frame(tab_font, bg=self.theme["panel"])
        floating_size_frame.grid(row=8, column=1, sticky="ew", pady=(0, 6))

        floating_size_scale = tk.Scale(
            floating_size_frame,
            from_=8,
            to=24,
            orient=tk.HORIZONTAL,
            variable=floating_font_size_var,
            bg=self.theme["panel"],
            fg=self.theme["label_fg"],
            troughcolor=self.theme["entry_bg"],
            highlightbackground=self.theme["panel"]
        )
        floating_size_scale.pack(side=tk.LEFT, fill=tk.X, expand=True)

        floating_size_value_label = tk.Label(
            floating_size_frame,
            textvariable=floating_font_size_var,
            bg=self.theme["panel"],
            fg=self.theme["label_fg"],
            font=(get_selected_font(), 10, 'normal'),
            width=3
        )
        floating_size_value_label.pack(side=tk.RIGHT, padx=(10, 0))

        # Floating window font bold toggle
        floating_font_bold_var = tk.BooleanVar(value=tsettings.get("floating_font_bold", True))
        tk.Label(tab_font, text="Bold Text", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).grid(row=9, column=0, sticky="w")

        floating_bold_check = tk.Checkbutton(
            tab_font,
            variable=floating_font_bold_var,
            bg=self.theme["panel"],
            activebackground=self.theme["panel"],
            selectcolor=self.theme["panel"]
        )
        floating_bold_check.grid(row=9, column=1, sticky="w", pady=(0, 6))

        # Floating window font preview
        floating_preview_frame = tk.Frame(tab_font, bg=self.theme["panel"])
        floating_preview_frame.grid(row=10, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        tk.Label(floating_preview_frame, text="Floating Window Preview:", bg=self.theme["panel"], fg=self.theme["label_fg"], font=(get_selected_font(), 10, 'normal')).pack(anchor="w")

        floating_preview_text = tk.Label(
            floating_preview_frame,
            text="Original: When I was young, I listened to the radio...\nTranslation: 当我年轻的时候，我听着收音机...",
            bg=self.theme["entry_bg"],
            fg=self.theme["entry_fg"],
            font=(floating_font_var.get(), floating_font_size_var.get(), 'bold' if floating_font_bold_var.get() else 'normal'),
            relief=tk.FLAT,
            padx=10,
            pady=10,
            wraplength=600,
            justify='left'
        )
        floating_preview_text.pack(fill=tk.X, pady=(5, 0))

        # Update floating preview when any floating setting changes
        def update_floating_preview(*_):
            weight = 'bold' if floating_font_bold_var.get() else 'normal'
            floating_preview_text.config(font=(floating_font_var.get(), floating_font_size_var.get(), weight))

        floating_font_var.trace_add("write", update_floating_preview)
        floating_font_size_var.trace_add("write", update_floating_preview)
        floating_font_bold_var.trace_add("write", update_floating_preview)

        tab_font.grid_columnconfigure(1, weight=1)

        # Footer buttons shared (Cancel/Save All)
        footer = tk.Frame(self, bg=self.theme["panel"]) 
        footer.pack(fill=tk.X, pady=(12, 12))

        cancel_btn = tk.Button(footer, text="Cancel", command=self._on_cancel, bg=self.theme["button_bg"], fg=self.theme["button_fg"], relief=tk.FLAT, padx=16, pady=8, cursor="hand2", font=(get_selected_font(), 10, 'normal'))
        cancel_btn.pack(side=tk.RIGHT, padx=(0, 8))

        # Save applies both tabs
        save_btn = tk.Button(footer, text="Save", command=on_save_translation, bg=self.theme["accent"], fg=self.theme["button_fg"], activebackground=self.theme["accent_active"], relief=tk.FLAT, padx=16, pady=8, cursor="hand2", font=(get_selected_font(), 10, 'normal'))
        save_btn.pack(side=tk.RIGHT)

        self.bind("<Return>", lambda e: self._on_save())
        self.bind("<Escape>", lambda e: self._on_cancel())

    def _collect_values(self) -> Dict[str, str]:
        return {k: v.get().strip() for k, v in self.vars.items()}

    def _on_save(self) -> None:
        # obsolete: we route through on_save_translation in the footer
        self.grab_release()
        self.destroy()

    def _on_cancel(self) -> None:
        self.grab_release()
        self.destroy()
