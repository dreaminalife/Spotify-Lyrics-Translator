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
    }


def read_translation_settings() -> Dict[str, Any]:
    path = get_translation_settings_path()
    if not path.exists():
        return default_translation_settings()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
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


