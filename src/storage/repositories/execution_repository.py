from __future__ import annotations

from datetime import datetime

from src.shared.schemas.database import TaskNodeRecord, TaskNodeRunRecord, TaskRunRecord
from src.shared.schemas.enums import NodeStatus, TaskRunStatus

from .base import BaseRepository


class TaskRunRepository(BaseRepository[TaskRunRecord]):
    table_name = "task_runs"
    model_type = TaskRunRecord
    primary_key = "task_run_id"

    def get_by_thread(self, thread_id: str) -> TaskRunRecord | None:
        rows = self.fetch_models(
            "SELECT * FROM task_runs WHERE thread_id = ? LIMIT 1",
            (thread_id,),
        )
        return rows[0] if rows else None

    def list_by_task(self, task_id: str) -> list[TaskRunRecord]:
        return self.fetch_models(
            """
            SELECT * FROM task_runs
            WHERE task_id = ?
            ORDER BY run_no ASC
            """,
            (task_id,),
        )

    def next_run_no(self, task_id: str) -> int:
        current = self.db.scalar(
            "SELECT COALESCE(MAX(run_no), 0) FROM task_runs WHERE task_id = ?",
            (task_id,),
        )
        return int(current or 0) + 1

    def update_status(
        self,
        task_run_id: str,
        status: TaskRunStatus,
        updated_at: datetime,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        summary_text: str | None = None,
        error_json: dict | None = None,
        last_checkpoint_at: datetime | None = None,
    ) -> None:
        updates: dict[str, object] = {
            "status": status,
            "updated_at": updated_at,
        }
        if started_at is not None:
            updates["started_at"] = started_at
        if completed_at is not None:
            updates["completed_at"] = completed_at
        if summary_text is not None:
            updates["summary_text"] = summary_text
        if error_json is not None:
            updates["error_json"] = error_json
        if last_checkpoint_at is not None:
            updates["last_checkpoint_at"] = last_checkpoint_at
        self.update_fields(task_run_id, updates)


class TaskNodeRepository(BaseRepository[TaskNodeRecord]):
    table_name = "task_nodes"
    model_type = TaskNodeRecord
    primary_key = "node_id"

    def insert_many(self, nodes: list[TaskNodeRecord]) -> None:
        for node in nodes:
            self.insert(node)

    def list_by_run(self, task_run_id: str) -> list[TaskNodeRecord]:
        return self.fetch_models(
            """
            SELECT * FROM task_nodes
            WHERE task_run_id = ?
            ORDER BY COALESCE(order_index, 999999), created_at ASC
            """,
            (task_run_id,),
        )

    def list_by_status(self, task_run_id: str, status: NodeStatus) -> list[TaskNodeRecord]:
        return self.fetch_models(
            """
            SELECT * FROM task_nodes
            WHERE task_run_id = ? AND status = ?
            ORDER BY COALESCE(order_index, 999999), created_at ASC
            """,
            (task_run_id, status.value),
        )

    def list_runnable_run_ids(self, limit: int = 20) -> list[str]:
        rows = self.db.fetchall(
            """
            SELECT DISTINCT tn.task_run_id
            FROM task_nodes tn
            INNER JOIN task_runs tr ON tr.task_run_id = tn.task_run_id
            WHERE tn.status = 'ready' AND tr.status = 'running'
            ORDER BY tn.updated_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [str(row["task_run_id"]) for row in rows]

    def update_status(
        self,
        node_id: str,
        status: NodeStatus,
        updated_at: datetime,
        *,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> None:
        updates: dict[str, object] = {
            "status": status,
            "updated_at": updated_at,
        }
        if started_at is not None:
            updates["started_at"] = started_at
        if completed_at is not None:
            updates["completed_at"] = completed_at
        self.update_fields(node_id, updates)


class TaskNodeRunRepository(BaseRepository[TaskNodeRunRecord]):
    table_name = "task_node_runs"
    model_type = TaskNodeRunRecord
    primary_key = "node_run_id"

    def list_by_node(self, node_id: str) -> list[TaskNodeRunRecord]:
        return self.fetch_models(
            """
            SELECT * FROM task_node_runs
            WHERE node_id = ?
            ORDER BY attempt_no ASC
            """,
            (node_id,),
        )

    def latest_for_node(self, node_id: str) -> TaskNodeRunRecord | None:
        rows = self.fetch_models(
            """
            SELECT * FROM task_node_runs
            WHERE node_id = ?
            ORDER BY attempt_no DESC
            LIMIT 1
            """,
            (node_id,),
        )
        return rows[0] if rows else None
