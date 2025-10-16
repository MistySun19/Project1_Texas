"""
Logging helpers that write deterministic NDJSON event streams.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class NDJSONLogger:
    """
    Writes JSON records to a file, one per line.

    The writer always injects an ISO timestamp and keeps field ordering stable
    by serialising through Python's json module with sort_keys=True.
    """

    def __init__(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._file = path.open("w", encoding="utf-8")

    def log(self, event_type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "payload": payload or {},
        }
        self._file.write(json.dumps(record, sort_keys=True) + "\n")
        self._file.flush()

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> "NDJSONLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
