"""Logging as one JSON object per line.

Every field passed with `extra={...}` becomes a top-level key, so log tools
(App Insights, Log Analytics, `jq`) can filter on `vehicle_type`, `records`, etc.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Attributes every LogRecord has. Anything else on a record came from `extra=`.
_STANDARD_ATTRS = frozenset(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "taskName",
}

_HANDLER_NAME = "ztm_ingest_json"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        doc: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                doc[key] = value
        if record.exc_info:
            doc["exc_info"] = self.formatException(record.exc_info)
        # default=str: values json can't encode (paths, datetimes) are written as text
        # instead of crashing the program.
        return json.dumps(doc, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Send all log records to stderr as JSON lines.

    Safe to call more than once: it replaces only its own handler and leaves other
    handlers (e.g. pytest's log capture) in place.
    """
    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)

    handler = logging.StreamHandler()
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
