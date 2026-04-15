from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping

from pydantic import BaseModel


def _format_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def serialize_db_value(key: str, value: Any) -> Any:
    if value is None:
        return None
    if key.endswith("_json"):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, datetime):
        return _format_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bool):
        return int(value)
    return value


def serialize_model(model: BaseModel) -> dict[str, Any]:
    raw = model.model_dump(mode="python")
    return {key: serialize_db_value(key, value) for key, value in raw.items()}


def serialize_updates(updates: Mapping[str, Any]) -> dict[str, Any]:
    return {key: serialize_db_value(key, value) for key, value in updates.items()}


def deserialize_row(row: sqlite3.Row | Mapping[str, Any]) -> dict[str, Any]:
    mapping = dict(row)
    output: dict[str, Any] = {}
    for key, value in mapping.items():
        if value is None:
            output[key] = None
            continue
        if key.endswith("_json") and isinstance(value, str):
            output[key] = json.loads(value)
            continue
        output[key] = value
    return output
