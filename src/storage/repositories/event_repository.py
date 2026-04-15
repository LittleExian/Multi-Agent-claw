from __future__ import annotations

from src.shared.schemas.database import TaskEventRecord

from .base import BaseRepository


class TaskEventRepository(BaseRepository[TaskEventRecord]):
    table_name = "task_events"
    model_type = TaskEventRecord
    primary_key = "event_id"

    def next_sequence(self, task_run_id: str | None) -> int:
        if task_run_id is None:
            return 0
        current = self.db.scalar(
            "SELECT COALESCE(MAX(event_seq), 0) FROM task_events WHERE task_run_id = ?",
            (task_run_id,),
        )
        return int(current or 0) + 1

    def list_by_run(
        self,
        task_run_id: str,
        *,
        after_seq: int | None = None,
        limit: int = 500,
    ) -> list[TaskEventRecord]:
        if after_seq is None:
            sql = """
                SELECT * FROM task_events
                WHERE task_run_id = ?
                ORDER BY event_seq ASC
                LIMIT ?
            """
            params = (task_run_id, limit)
        else:
            sql = """
                SELECT * FROM task_events
                WHERE task_run_id = ? AND event_seq > ?
                ORDER BY event_seq ASC
                LIMIT ?
            """
            params = (task_run_id, after_seq, limit)
        return self.fetch_models(sql, params)

    def list_by_session(self, session_id: str, limit: int = 500) -> list[TaskEventRecord]:
        return self.fetch_models(
            """
            SELECT * FROM task_events
            WHERE session_id = ?
            ORDER BY occurred_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        )

    def append(self, event: TaskEventRecord) -> TaskEventRecord:
        self.insert(event)
        return event
