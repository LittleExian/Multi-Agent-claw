from __future__ import annotations

from src.shared.schemas.database import MessageAttachmentRecord, MessageRecord

from .base import BaseRepository


class MessageRepository(BaseRepository[MessageRecord]):
    table_name = "messages"
    model_type = MessageRecord
    primary_key = "message_id"

    def list_by_session(self, session_id: str, limit: int = 100) -> list[MessageRecord]:
        return self.fetch_models(
            """
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (session_id, limit),
        )

    def list_by_task_run(self, task_run_id: str) -> list[MessageRecord]:
        return self.fetch_models(
            """
            SELECT * FROM messages
            WHERE task_run_id = ?
            ORDER BY created_at ASC
            """,
            (task_run_id,),
        )


class MessageAttachmentRepository(BaseRepository[MessageAttachmentRecord]):
    table_name = "message_attachments"
    model_type = MessageAttachmentRecord
    primary_key = "attachment_id"

    def list_by_message(self, message_id: str) -> list[MessageAttachmentRecord]:
        return self.fetch_models(
            """
            SELECT * FROM message_attachments
            WHERE message_id = ?
            ORDER BY created_at ASC
            """,
            (message_id,),
        )
