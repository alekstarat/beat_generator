"""
App config — last sample pack path, window geometry, defaults.

Stored as JSON next to the project (or in user config dir).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Prefer project-local config so the prototype is portable.
_CONFIG_PATH = Path(__file__).resolve().parent.parent / "beat_generator_config.json"


def config_path() -> Path:
    return _CONFIG_PATH


def load_config() -> dict[str, Any]:
    path = _CONFIG_PATH
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(data: dict[str, Any]) -> None:
    path = _CONFIG_PATH
    try:
        existing = load_config()
        existing.update(data)
        path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_last_pack() -> Optional[Path]:
    raw = load_config().get("last_sample_pack")
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_dir() else None


def set_last_pack(path: Path) -> None:
    save_config({"last_sample_pack": str(path.resolve())})


def get_last_settings() -> dict[str, Any]:
    return load_config().get("last_settings") or {}


def set_last_settings(settings: dict[str, Any]) -> None:
    save_config({"last_settings": settings})
