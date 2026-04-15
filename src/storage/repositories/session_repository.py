from __future__ import annotations

from datetime import datetime

from src.shared.schemas.database import SessionCompactionRecord, SessionRecord

from .base import BaseRepository


class SessionRepository(BaseRepository[SessionRecord]):
    table_name = "sessions"
    model_type = SessionRecord
    primary_key = "session_id"

    def list_by_user(
        self,
        user_id: str,
        channel: str | None = None,
        limit: int = 50,
    ) -> list[SessionRecord]:
        if channel is None:
            sql = """
                SELECT * FROM sessions
                WHERE user_id = ?
                ORDER BY COALESCE(last_message_at, created_at) DESC
                LIMIT ?
            """
            params = (user_id, limit)
        else:
            sql = """
                SELECT * FROM sessions
                WHERE user_id = ? AND channel = ?
                ORDER BY COALESCE(last_message_at, created_at) DESC
                LIMIT ?
            """
            params = (user_id, channel, limit)
        return self.fetch_models(sql, params)

    def touch(self, session_id: str, at: datetime) -> None:
        self.update_fields(
            session_id,
            {
                "last_message_at": at,
                "updated_at": at,
            },
        )


class SessionCompactionRepository(BaseRepository[SessionCompactionRecord]):
    table_name = "session_compactions"
    model_type = SessionCompactionRecord
    primary_key = "compaction_id"

    def list_by_session(self, session_id: str, limit: int = 50) -> list[SessionCompactionRecord]:
        return self.fetch_models(
            """
            SELECT * FROM session_compactions
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
