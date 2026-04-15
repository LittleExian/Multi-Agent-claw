from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

JSONDict = dict[str, Any]
JSONList = list[Any]

SCHEMA_VERSION = "2026-04-13"


class SwarmSchema(BaseModel):
    """Base schema for shared SwarmOS models."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        populate_by_name=True,
    )


class TimestampedSchema(SwarmSchema):
    created_at: datetime


class MutableTimestampedSchema(TimestampedSchema):
    updated_at: datetime


def json_dict_field() -> Any:
    return Field(default_factory=dict)


def json_list_field() -> Any:
    return Field(default_factory=list)
