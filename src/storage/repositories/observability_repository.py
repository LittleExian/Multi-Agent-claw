from __future__ import annotations

from src.shared.schemas.database import (
    AuditLogRecord,
    LLMCallRecord,
    SandboxRunRecord,
    ToolCallRecord,
)

from .base import BaseRepository


class LLMCallRepository(BaseRepository[LLMCallRecord]):
    table_name = "llm_calls"
    model_type = LLMCallRecord
    primary_key = "llm_call_id"

    def list_by_run(self, task_run_id: str) -> list[LLMCallRecord]:
        return self.fetch_models(
            """
            SELECT * FROM llm_calls
            WHERE task_run_id = ?
            ORDER BY started_at ASC
            """,
            (task_run_id,),
        )


class ToolCallRepository(BaseRepository[ToolCallRecord]):
    table_name = "tool_calls"
    model_type = ToolCallRecord
    primary_key = "tool_call_id"

    def list_by_run(self, task_run_id: str) -> list[ToolCallRecord]:
        return self.fetch_models(
            """
            SELECT * FROM tool_calls
            WHERE task_run_id = ?
            ORDER BY started_at ASC
            """,
            (task_run_id,),
        )


class SandboxRunRepository(BaseRepository[SandboxRunRecord]):
    table_name = "sandbox_runs"
    model_type = SandboxRunRecord
    primary_key = "sandbox_run_id"

    def list_by_tool_call(self, tool_call_id: str) -> list[SandboxRunRecord]:
        return self.fetch_models(
            """
            SELECT * FROM sandbox_runs
            WHERE tool_call_id = ?
            ORDER BY started_at ASC
            """,
            (tool_call_id,),
        )


class AuditLogRepository(BaseRepository[AuditLogRecord]):
    table_name = "audit_log"
    model_type = AuditLogRecord
    primary_key = "audit_id"

    def list_by_run(self, task_run_id: str) -> list[AuditLogRecord]:
        return self.fetch_models(
            """
            SELECT * FROM audit_log
            WHERE task_run_id = ?
            ORDER BY created_at ASC
            """,
            (task_run_id,),
        )
