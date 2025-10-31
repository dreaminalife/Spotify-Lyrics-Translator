from __future__ import annotations

from pathlib import Path
from typing import Dict, Any, Tuple
import json


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_translation_settings_path() -> Path:
    return _project_root() / "translation_settings.json"


def get_models_config_path() -> Path:
    return _project_root() / "openrouter_models.json"


DEFAULT_PROMPT = (
    "Translate the following song lyrics to {target_language}. "
    "Keep line breaks, return exactly the same number of lines in the same order. "
    "Output ONLY the translations, one line per input line, no numbering, no extra text.\n\n{lyrics}"
)


# Universal default model parameters applied to all OpenRouter models unless overridden
DEFAULT_MODEL_PARAMS = {
    "temperature": 0.2,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tokens": 512,
}


def default_translation_settings() -> Dict[str, Any]:
    return {
        "provider": "Google Translate",  # or "OpenRouter"
        "selected_model": "openrouter/auto",
        "target_language": "en",
        "global_prompt": DEFAULT_PROMPT,
        "selected_font": "Microsoft YaHei UI",  # Default Chinese font (will be updated after tkinter init)
        "font_size": 12,  # Default font size
        "font_bold": True,  # Default to bold fonts
        # Floating window font settings
        "floating_font": "Microsoft YaHei UI",  # Default floating window font
        "floating_font_size": 12,  # Default floating window font size
        "floating_font_bold": True,  # Default floating window bold setting
        # Floating window persisted size
        "floating_window_width": 800,
        "floating_window_height": 200,
        # Theme colors (Spotify-inspired defaults)
        # Global & Text
        "accent_primary": "#1DB954",
        "accent_hover": "#1ED760",
        "accent_active": "#1AA34A",
        "text_primary": "#FFFFFF",
        "text_muted": "#B3B3B3",
        "text_inverse": "#121212",
        # Windows & Panels
        "main_bg": "#121212",
        "panel_bg": "#181818",
        "frame_bg": "#121212",
        # Inputs
        "entry_bg": "#282828",
        "entry_fg": "#FFFFFF",
        "entry_caret": "#FFFFFF",
        # Buttons
        "button_primary_bg": "#1DB954",
        "button_primary_fg": "#FFFFFF",
        "button_primary_hover": "#1ED760",
        "button_primary_active": "#1AA34A",
        "button_secondary_bg": "#282828",
        "button_secondary_fg": "#FFFFFF",
        "button_secondary_hover": "#B3B3B3",
        "button_secondary_active": "#B3B3B3",
        # Lyrics Table
        "lyrics_table_bg": "#181818",
        "lyrics_row_odd_bg": "#181818",
        "lyrics_row_even_bg": "#282828",
        "lyrics_heading_bg": "#282828",
        "lyrics_heading_fg": "#FFFFFF",
        "lyrics_selected_bg": "#1DB954",
        "lyrics_selected_fg": "#FFFFFF",
        "lyrics_text_fg": "#FFFFFF",
        # Scrollbar
        "scrollbar_bg": "#282828",
        "scrollbar_trough": "#181818",
        "scrollbar_arrow": "#B3B3B3",
        "scrollbar_border": "#181818",
        # Floating Window
        "floating_bg": "#181818",
        "floating_border": "#1DB954",
        "floating_title_fg": "#1DB954",
        "floating_artist_fg": "#B3B3B3",
        "floating_original_fg": "#FFFFFF",
        "floating_translated_fg": "#FFFFFF",
        "floating_close_bg": "#181818",
        "floating_close_fg": "#B3B3B3",
        # Backward compatibility
        "main_bg_color": "#121212",
        "floating_bg_color": "#181818",
    }


def read_translation_settings() -> Dict[str, Any]:
    path = get_translation_settings_path()
    if not path.exists():
        return default_translation_settings()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        # Ensure selected_font is set if not present (for backward compatibility)
        # This will be updated later when tkinter is ready
        if "selected_font" not in settings:
            settings["selected_font"] = "Microsoft YaHei UI"  # Safe fallback
        if "main_bg_color" not in settings:
            settings["main_bg_color"] = "#121212"
        if "floating_bg_color" not in settings:
            settings["floating_bg_color"] = "#181818"
        return settings
    except Exception:
        return default_translation_settings()


def save_translation_settings(values: Dict[str, Any]) -> None:
    path = get_translation_settings_path()
    # Merge with defaults to keep keys
    base = default_translation_settings()
    base.update(values or {})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_theme_colors() -> Dict[str, str]:
    """Return the current theme colors for main and floating windows."""
    settings = read_translation_settings()
    return {
        # Global & Text
        "accent_primary": settings.get("accent_primary", "#1DB954"),
        "accent_hover": settings.get("accent_hover", "#1ED760"),
        "accent_active": settings.get("accent_active", "#1AA34A"),
        "text_primary": settings.get("text_primary", "#FFFFFF"),
        "text_muted": settings.get("text_muted", "#B3B3B3"),
        "text_inverse": settings.get("text_inverse", "#121212"),
        # Windows & Panels
        "main_bg": settings.get("main_bg", "#121212"),
        "panel_bg": settings.get("panel_bg", "#181818"),
        "frame_bg": settings.get("frame_bg", "#121212"),
        # Inputs
        "entry_bg": settings.get("entry_bg", "#282828"),
        "entry_fg": settings.get("entry_fg", "#FFFFFF"),
        "entry_caret": settings.get("entry_caret", "#FFFFFF"),
        # Buttons
        "button_primary_bg": settings.get("button_primary_bg", "#1DB954"),
        "button_primary_fg": settings.get("button_primary_fg", "#FFFFFF"),
        "button_primary_hover": settings.get("button_primary_hover", "#1ED760"),
        "button_primary_active": settings.get("button_primary_active", "#1AA34A"),
        "button_secondary_bg": settings.get("button_secondary_bg", "#282828"),
        "button_secondary_fg": settings.get("button_secondary_fg", "#FFFFFF"),
        "button_secondary_hover": settings.get("button_secondary_hover", "#B3B3B3"),
        "button_secondary_active": settings.get("button_secondary_active", "#B3B3B3"),
        # Lyrics Table
        "lyrics_table_bg": settings.get("lyrics_table_bg", "#181818"),
        "lyrics_row_odd_bg": settings.get("lyrics_row_odd_bg", "#181818"),
        "lyrics_row_even_bg": settings.get("lyrics_row_even_bg", "#282828"),
        "lyrics_heading_bg": settings.get("lyrics_heading_bg", "#282828"),
        "lyrics_heading_fg": settings.get("lyrics_heading_fg", "#FFFFFF"),
        "lyrics_selected_bg": settings.get("lyrics_selected_bg", "#1DB954"),
        "lyrics_selected_fg": settings.get("lyrics_selected_fg", "#FFFFFF"),
        "lyrics_text_fg": settings.get("lyrics_text_fg", "#FFFFFF"),
        # Scrollbar
        "scrollbar_bg": settings.get("scrollbar_bg", "#282828"),
        "scrollbar_trough": settings.get("scrollbar_trough", "#181818"),
        "scrollbar_arrow": settings.get("scrollbar_arrow", "#B3B3B3"),
        "scrollbar_border": settings.get("scrollbar_border", "#181818"),
        # Floating Window
        "floating_bg": settings.get("floating_bg", "#181818"),
        "floating_border": settings.get("floating_border", "#1DB954"),
        "floating_title_fg": settings.get("floating_title_fg", "#1DB954"),
        "floating_artist_fg": settings.get("floating_artist_fg", "#B3B3B3"),
        "floating_original_fg": settings.get("floating_original_fg", "#FFFFFF"),
        "floating_translated_fg": settings.get("floating_translated_fg", "#FFFFFF"),
        "floating_close_bg": settings.get("floating_close_bg", "#181818"),
        "floating_close_fg": settings.get("floating_close_fg", "#B3B3B3"),
        # Backward compatibility
        "main_bg_color": settings.get("main_bg_color", "#121212"),
        "floating_bg_color": settings.get("floating_bg_color", "#181818"),
    }


def default_models_config() -> Dict[str, Any]:
    # Empty by default; users can add bodies per model
    return {}


def read_models_config() -> Dict[str, Any]:
    path = get_models_config_path()
    if not path.exists():
        return default_models_config()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default_models_config()


def save_models_config(values: Dict[str, Any]) -> None:
    path = get_models_config_path()
    base = default_models_config()
    base.update(values or {})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(base, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


