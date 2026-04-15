from __future__ import annotations

from src.shared.schemas.database import ArtifactRecord

from .base import BaseRepository


class ArtifactRepository(BaseRepository[ArtifactRecord]):
    table_name = "artifacts"
    model_type = ArtifactRecord
    primary_key = "artifact_id"

    def list_by_run(self, task_run_id: str) -> list[ArtifactRecord]:
        return self.fetch_models(
            """
            SELECT * FROM artifacts
            WHERE task_run_id = ?
            ORDER BY created_at ASC
            """,
            (task_run_id,),
        )

    def list_by_message(self, message_id: str) -> list[ArtifactRecord]:
        return self.fetch_models(
            """
            SELECT * FROM artifacts
            WHERE source_message_id = ?
            ORDER BY created_at ASC
            """,
            (message_id,),
        )
