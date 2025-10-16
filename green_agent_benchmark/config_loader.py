"""
Configuration loader with YAML fallback to JSON.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any, Dict

try:
    import yaml
except ImportError:  # pragma: no cover - optional dependency
    yaml = None  # type: ignore


def load_config(path: str | pathlib.Path) -> Dict[str, Any]:
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix in {".yaml", ".yml"} and yaml is not None:
        return yaml.safe_load(text)
    return json.loads(text)
