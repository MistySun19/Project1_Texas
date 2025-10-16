"""
Lightweight .env loader to avoid extra dependencies.

Reads KEY=VALUE pairs (ignoring blank lines and comments) and injects them into
`os.environ` if the key is not already set.
"""

from __future__ import annotations

import os
import pathlib
from typing import Iterable


def load_env(path: str | pathlib.Path = ".env") -> None:
    env_path = pathlib.Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or key in os.environ:
            continue
        os.environ[key] = value
