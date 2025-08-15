from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from app.config import BASE_DIR, register_reload_hook

APPS: Dict[str, dict] = {}
COMBOS: Dict[str, List[List[str]]] = {}


def _load() -> None:
    """Load applications and combos definitions from JSON files."""
    global APPS, COMBOS
    try:
        with open(Path(BASE_DIR) / "apps.json", "r", encoding="utf-8") as fh:
            apps_list = json.load(fh) or []
            APPS = {item.get("id"): item for item in apps_list if item.get("id")}
    except Exception:
        APPS = {}
    try:
        with open(Path(BASE_DIR) / "combos.json", "r", encoding="utf-8") as fh:
            COMBOS = json.load(fh) or {}
    except Exception:
        COMBOS = {}


def reload_definitions(_settings: object | None = None) -> None:
    _load()


# Initial load
_load()
register_reload_hook(reload_definitions)
