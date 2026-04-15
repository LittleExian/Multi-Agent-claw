from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from src.shared.schemas import TaskEventRecord
from src.storage import SQLiteDatabase
from src.storage.repositories import (
    ApprovalRepository,
    ArtifactRepository,
    AuditLogRepository,
    LLMCallRepository,
    MemoryEntryRepository,
    MessageAttachmentRepository,
    MessageRepository,
    SandboxRunRepository,
    SessionCompactionRepository,
    SessionRepository,
    SkillCandidateRepository,
    SkillCatalogSnapshotRepository,
    TaskEventRepository,
    TaskNodeRepository,
    TaskNodeRunRepository,
    TaskRepository,
    TaskRunRepository,
    ToolCallRepository,
)


class SQLiteUnitOfWork:
    """Groups repository calls into a single SQLite transaction."""

    def __init__(
        self,
        db: SQLiteDatabase,
        *,
        event_publisher: Callable[[TaskEventRecord], None] | None = None,
    ):
        self.db = db
        self._event_publisher = event_publisher
        self.sessions = SessionRepository(db)
        self.session_compactions = SessionCompactionRepository(db)
        self.messages = MessageRepository(db)
        self.message_attachments = MessageAttachmentRepository(db)
        self.tasks = TaskRepository(db)
        self.task_runs = TaskRunRepository(db)
        self.task_nodes = TaskNodeRepository(db)
        self.task_node_runs = TaskNodeRunRepository(db)
        self.approvals = ApprovalRepository(db)
        self.artifacts = ArtifactRepository(db)
        self.task_events = TaskEventRepository(db)
        self.llm_calls = LLMCallRepository(db)
        self.tool_calls = ToolCallRepository(db)
        self.sandbox_runs = SandboxRunRepository(db)
        self.audit_logs = AuditLogRepository(db)
        self.memory_entries = MemoryEntryRepository(db)
        self.skill_candidates = SkillCandidateRepository(db)
        self.skill_catalog_snapshots = SkillCatalogSnapshotRepository(db)
        self._tx = None
        self._pending_events: list[TaskEventRecord] = []

    def __enter__(self) -> "SQLiteUnitOfWork":
        self._tx = self.db.transaction()
        self._tx.__enter__()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        assert self._tx is not None
        result = self._tx.__exit__(exc_type, exc, tb)
        try:
            if exc_type is None and exc is None and self._event_publisher is not None:
                for event in self._pending_events:
                    try:
                        self._event_publisher(event)
                    except Exception:
                        # Event fanout is best-effort; the database remains the source of truth.
                        continue
        finally:
            self._pending_events.clear()
        return result

    def collect_emitted_event(self, event: TaskEventRecord) -> None:
        self._pending_events.append(event)


def build_uow_factory(
    db: SQLiteDatabase,
    *,
    event_publisher: Callable[[TaskEventRecord], None] | None = None,
) -> Callable[[], SQLiteUnitOfWork]:
    def _factory() -> SQLiteUnitOfWork:
        return SQLiteUnitOfWork(db, event_publisher=event_publisher)

    return _factory
