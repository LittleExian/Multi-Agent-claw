from __future__ import annotations

from collections.abc import Callable

from src.shared.schemas import EventLevel, TaskEventRecord, TaskEventType, VisibilityScope

from .uow import SQLiteUnitOfWork
from .utils import generate_prefixed_id, utc_now


class ServiceBase:
    def __init__(self, uow_factory: Callable[[], SQLiteUnitOfWork]):
        self.uow_factory = uow_factory

    def _emit_event(
        self,
        uow: SQLiteUnitOfWork,
        *,
        event_type: TaskEventType,
        session_id: str,
        task_id: str | None = None,
        task_run_id: str | None = None,
        node_id: str | None = None,
        approval_id: str | None = None,
        emitted_by: str,
        payload_json: dict | None = None,
        event_level: EventLevel = EventLevel.INFO,
        visibility_scope: VisibilityScope = VisibilityScope.USER,
        trace_id: str | None = None,
        causation_event_id: str | None = None,
    ) -> TaskEventRecord:
        now = utc_now()
        event = TaskEventRecord(
            event_id=generate_prefixed_id("evt"),
            task_id=task_id,
            task_run_id=task_run_id,
            session_id=session_id,
            node_id=node_id,
            approval_id=approval_id,
            trace_id=trace_id,
            event_seq=uow.task_events.next_sequence(task_run_id),
            event_type=event_type.value,
            event_level=event_level,
            visibility_scope=visibility_scope,
            emitted_by=emitted_by,
            causation_event_id=causation_event_id,
            payload_json=payload_json or {},
            occurred_at=now,
            persisted_at=now,
        )
        uow.task_events.append(event)
        uow.collect_emitted_event(event)
        return event
