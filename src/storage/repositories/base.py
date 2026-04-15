from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar

from pydantic import BaseModel

from ..serialization import deserialize_row, serialize_model, serialize_updates
from ..sqlite import SQLiteDatabase

ModelT = TypeVar("ModelT", bound=BaseModel)


class BaseRepository(Generic[ModelT]):
    table_name: str
    model_type: type[ModelT]
    primary_key: str

    def __init__(self, db: SQLiteDatabase):
        self.db = db

    def _row_to_model(self, row: Any) -> ModelT:
        payload = deserialize_row(row)
        return self.model_type.model_validate(payload)

    def get(self, primary_value: str) -> ModelT | None:
        row = self.db.fetchone(
            f"SELECT * FROM {self.table_name} WHERE {self.primary_key} = ?",
            (primary_value,),
        )
        if row is None:
            return None
        return self._row_to_model(row)

    def delete(self, primary_value: str) -> None:
        self.db.execute(
            f"DELETE FROM {self.table_name} WHERE {self.primary_key} = ?",
            (primary_value,),
        )

    def insert(self, record: ModelT) -> ModelT:
        data = serialize_model(record)
        columns = list(data.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {self.table_name} ({', '.join(columns)}) "
            f"VALUES ({placeholders})"
        )
        self.db.execute(sql, tuple(data[column] for column in columns))
        return record

    def update_fields(self, primary_value: str, updates: dict[str, Any]) -> None:
        if not updates:
            return
        serialized = serialize_updates(updates)
        assignments = ", ".join(f"{column} = ?" for column in serialized)
        params = list(serialized.values()) + [primary_value]
        self.db.execute(
            f"UPDATE {self.table_name} SET {assignments} WHERE {self.primary_key} = ?",
            tuple(params),
        )

    def fetch_models(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
    ) -> list[ModelT]:
        rows = self.db.fetchall(sql, params)
        return [self._row_to_model(row) for row in rows]
