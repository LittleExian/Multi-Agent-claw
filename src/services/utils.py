from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_prefixed_id(prefix: str) -> str:
    clean = prefix[:-1] if prefix.endswith("_") else prefix
    return f"{clean}_{uuid4().hex}"


def compact_text(value: str, max_length: int = 80) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "..."
