from __future__ import annotations

from datetime import datetime

from src.shared.schemas.database import TaskRecord
from src.shared.schemas.enums import TaskStatus

from .base import BaseRepository


class TaskRepository(BaseRepository[TaskRecord]):
    table_name = "tasks"
    model_type = TaskRecord
    primary_key = "task_id"

    def list_recent(self, limit: int = 20) -> list[TaskRecord]:
        return self.fetch_models(
            """
            SELECT * FROM tasks
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    def list_by_session(self, session_id: str, limit: int = 20) -> list[TaskRecord]:
        return self.fetch_models(
            """
            SELECT * FROM tasks
            WHERE session_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        )

    def list_by_status(self, status: TaskStatus, limit: int = 100) -> list[TaskRecord]:
        return self.fetch_models(
            """
            SELECT * FROM tasks
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (status.value, limit),
        )

    def latest_active_for_session(self, session_id: str) -> TaskRecord | None:
        rows = self.fetch_models(
            """
            SELECT * FROM tasks
            WHERE session_id = ?
              AND status NOT IN ('completed', 'failed', 'cancelled')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (session_id,),
        )
        return rows[0] if rows else None

    def set_current_run(
        self,
        task_id: str,
        *,
        current_run_id: str | None,
        latest_run_id: str,
        status: TaskStatus,
        updated_at: datetime,
        completed_at: datetime | None = None,
    ) -> None:
        self.update_fields(
            task_id,
            {
                "current_run_id": current_run_id,
                "latest_run_id": latest_run_id,
                "status": status,
                "updated_at": updated_at,
                "completed_at": completed_at,
            },
        )
