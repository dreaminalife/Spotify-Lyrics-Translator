from pathlib import Path
from typing import Dict, Tuple

REQUIRED_KEYS = ["client_id", "client_secret", "redirect_uri", "sp_dc_cookie"]
# Optional keys we also persist if present (not required for validation)
OPTIONAL_KEYS = ["openrouter_api_key"]


def get_secrets_file_path() -> Path:
    """Return the absolute path to the root-level secrets.txt file."""
    # src/ -> project root
    return Path(__file__).resolve().parent.parent / "secrets.txt"


def read_secrets() -> Dict[str, str]:
    """Read key=value pairs from secrets.txt into a dict.

    Unknown keys are kept; blank lines and comments (# ...) are ignored.
    """
    secrets_path = get_secrets_file_path()
    secrets: Dict[str, str] = {}
    if not secrets_path.exists():
        return secrets

    try:
        content = secrets_path.read_text(encoding="utf-8")
    except Exception:
        return secrets

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        secrets[key.strip()] = value.strip()
    return secrets


def save_secrets(values: Dict[str, str]) -> None:
    """Write secrets to secrets.txt in key=value format, preserving only provided keys.

    Writes atomically by writing to a temp file and replacing.
    """
    secrets_path = get_secrets_file_path()
    lines = []
    # Write required keys first
    for key in REQUIRED_KEYS:
        val = values.get(key, "")
        lines.append(f"{key}={val}")
    # Then optional keys
    for key in OPTIONAL_KEYS:
        val = values.get(key, "")
        lines.append(f"{key}={val}")
    temp_path = secrets_path.with_suffix(".tmp")
    temp_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    temp_path.replace(secrets_path)


def validate_secrets(values: Dict[str, str]) -> Tuple[bool, list]:
    """Validate required keys are present and non-empty.

    Returns (is_valid, missing_keys)
    """
    missing = [k for k in REQUIRED_KEYS if not values.get(k)]
    return (len(missing) == 0, missing)
