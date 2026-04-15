from __future__ import annotations

from datetime import datetime

from src.shared.schemas.database import ApprovalRecord
from src.shared.schemas.enums import ApprovalStatus

from .base import BaseRepository


class ApprovalRepository(BaseRepository[ApprovalRecord]):
    table_name = "approvals"
    model_type = ApprovalRecord
    primary_key = "approval_id"

    def latest_for_node(self, node_id: str) -> ApprovalRecord | None:
        rows = self.fetch_models(
            """
            SELECT * FROM approvals
            WHERE node_id = ?
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (node_id,),
        )
        return rows[0] if rows else None

    def list_by_run(
        self,
        task_run_id: str,
        *,
        status: ApprovalStatus | None = None,
    ) -> list[ApprovalRecord]:
        if status is None:
            sql = """
                SELECT * FROM approvals
                WHERE task_run_id = ?
                ORDER BY requested_at ASC
            """
            params = (task_run_id,)
        else:
            sql = """
                SELECT * FROM approvals
                WHERE task_run_id = ? AND status = ?
                ORDER BY requested_at ASC
            """
            params = (task_run_id, status.value)
        return self.fetch_models(sql, params)

    def list_pending(self, *, task_run_id: str | None = None) -> list[ApprovalRecord]:
        if task_run_id is None:
            sql = """
                SELECT * FROM approvals
                WHERE status = 'pending'
                ORDER BY requested_at ASC
            """
            params = ()
        else:
            sql = """
                SELECT * FROM approvals
                WHERE task_run_id = ? AND status = 'pending'
                ORDER BY requested_at ASC
            """
            params = (task_run_id,)
        return self.fetch_models(sql, params)

    def resolve(
        self,
        approval_id: str,
        *,
        status: ApprovalStatus,
        decided_by: str,
        decided_at: datetime,
        decision_json: dict | None = None,
    ) -> None:
        updates: dict[str, object] = {
            "status": status,
            "decided_by": decided_by,
            "decided_at": decided_at,
        }
        if decision_json is not None:
            updates["decision_json"] = decision_json
        self.update_fields(approval_id, updates)
