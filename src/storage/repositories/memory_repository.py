from __future__ import annotations

from src.shared.schemas.database import (
    MemoryEntryRecord,
    SkillCandidateRecord,
    SkillCatalogSnapshotRecord,
)

from .base import BaseRepository


class MemoryEntryRepository(BaseRepository[MemoryEntryRecord]):
    table_name = "memory_entries"
    model_type = MemoryEntryRecord
    primary_key = "memory_id"

    def list_by_task(self, task_id: str) -> list[MemoryEntryRecord]:
        return self.fetch_models(
            """
            SELECT * FROM memory_entries
            WHERE task_id = ?
            ORDER BY created_at DESC
            """,
            (task_id,),
        )


class SkillCandidateRepository(BaseRepository[SkillCandidateRecord]):
    table_name = "skill_candidates"
    model_type = SkillCandidateRecord
    primary_key = "skill_candidate_id"

    def list_by_status(self, status: str) -> list[SkillCandidateRecord]:
        return self.fetch_models(
            """
            SELECT * FROM skill_candidates
            WHERE status = ?
            ORDER BY created_at DESC
            """,
            (status,),
        )


class SkillCatalogSnapshotRepository(BaseRepository[SkillCatalogSnapshotRecord]):
    table_name = "skill_catalog_snapshots"
    model_type = SkillCatalogSnapshotRecord
    primary_key = "snapshot_id"

    def list_by_skill_name(self, skill_name: str) -> list[SkillCatalogSnapshotRecord]:
        return self.fetch_models(
            """
            SELECT * FROM skill_catalog_snapshots
            WHERE skill_name = ?
            ORDER BY loaded_at DESC
            """,
            (skill_name,),
        )
