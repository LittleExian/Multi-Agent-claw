from __future__ import annotations

from src.application.api.schemas import (
    ApprovalRead,
    ArtifactRead,
    RunSnapshotResponse,
    SessionRead,
    TaskNodeRead,
    TaskRead,
    TaskRunRead,
)
from src.services.models import TaskLifecycleResult
from src.shared.schemas import (
    CORE_EVENT_PAYLOADS,
    CurrentNodeSnapshot,
    NodeStatus,
    TaskEventEnvelope,
    TaskEventType,
    TaskRunSnapshotPayload,
)


TERMINAL_NODE_STATUSES = {
    NodeStatus.COMPLETED,
    NodeStatus.FAILED,
    NodeStatus.SKIPPED,
    NodeStatus.CANCELLED,
}


def to_session_read(record) -> SessionRead:
    return SessionRead.model_validate(record.model_dump(mode="python"))


def to_artifact_read(record) -> ArtifactRead:
    return ArtifactRead.model_validate(record.model_dump(mode="python"))


def to_task_node_read(record) -> TaskNodeRead:
    return TaskNodeRead(
        node_id=record.node_id,
        step_key=record.step_key,
        role=record.role,
        title=record.title,
        goal=record.goal,
        status=record.status,
        order_index=record.order_index,
        depth=record.depth,
        approval_required=record.approval_required,
        dependencies=list(record.dependencies_json),
        tools_hint=list(record.tools_hint_json),
        outputs=list(record.outputs_json),
        metadata_json=record.metadata_json,
        started_at=record.started_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def build_task_run_read(uow, record, *, include_nodes: bool = True, include_artifacts: bool = True) -> TaskRunRead:
    nodes = []
    if include_nodes:
        nodes = [to_task_node_read(node) for node in uow.task_nodes.list_by_run(record.task_run_id)]
    artifacts = []
    if include_artifacts:
        artifacts = [to_artifact_read(artifact) for artifact in uow.artifacts.list_by_run(record.task_run_id)]
    return TaskRunRead(
        task_run_id=record.task_run_id,
        task_id=record.task_id,
        thread_id=record.thread_id,
        run_no=record.run_no,
        trigger_kind=record.trigger_kind,
        status=record.status,
        spec_json=record.spec_json,
        plan_json=record.plan_json,
        context_snapshot_json=record.context_snapshot_json,
        summary_text=record.summary_text,
        error_json=record.error_json,
        queue_wait_ms=record.queue_wait_ms,
        approval_wait_ms=record.approval_wait_ms,
        checkpoint_backend=record.checkpoint_backend,
        checkpoint_ref=record.checkpoint_ref,
        last_checkpoint_at=record.last_checkpoint_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        nodes=nodes,
        artifacts=artifacts,
    )


def build_task_read(
    uow,
    record,
    *,
    include_current_run: bool = True,
    include_latest_run: bool = True,
    include_nodes: bool = True,
) -> TaskRead:
    current_run = None
    latest_run = None
    if include_current_run and record.current_run_id:
        current_run_record = uow.task_runs.get(record.current_run_id)
        if current_run_record is not None:
            current_run = build_task_run_read(
                uow,
                current_run_record,
                include_nodes=include_nodes,
            )
    if include_latest_run and record.latest_run_id:
        if current_run is not None and record.current_run_id == record.latest_run_id:
            latest_run = current_run
        else:
            latest_run_record = uow.task_runs.get(record.latest_run_id)
            if latest_run_record is not None:
                latest_run = build_task_run_read(
                    uow,
                    latest_run_record,
                    include_nodes=include_nodes,
                )
    return TaskRead(
        task_id=record.task_id,
        session_id=record.session_id,
        source_message_id=record.source_message_id,
        title=record.title,
        objective=record.objective,
        task_kind=record.task_kind,
        status=record.status,
        priority=record.priority,
        complexity=record.complexity,
        risk_level=record.risk_level,
        current_run_id=record.current_run_id,
        latest_run_id=record.latest_run_id,
        success_criteria=list(record.success_criteria_json),
        constraints=list(record.constraints_json),
        expected_outputs=list(record.expected_outputs_json),
        metadata_json=record.metadata_json,
        created_by=record.created_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
        current_run=current_run,
        latest_run=latest_run,
    )


def to_approval_read(record) -> ApprovalRead:
    return ApprovalRead.model_validate(record.model_dump(mode="python"))


def build_task_lifecycle_result(
    uow,
    *,
    session_id: str,
    task_id: str | None,
    task_run_id: str | None,
    intake_kind=None,
) -> TaskLifecycleResult:
    task = uow.tasks.get(task_id) if task_id else None
    run = uow.task_runs.get(task_run_id) if task_run_id else None
    approval_id = None
    if task_run_id:
        pending = uow.approvals.list_pending(task_run_id=task_run_id)
        approval_id = pending[0].approval_id if pending else None
    status = task.status.value if task is not None else (run.status.value if run is not None else "unknown")
    return TaskLifecycleResult(
        session_id=session_id,
        intake_kind=intake_kind,
        task_id=task_id,
        task_run_id=task_run_id,
        status=status,
        approval_id=approval_id,
        requires_clarification=bool(task and task.status.value == "needs_clarification"),
    )


def to_task_event_envelope(record) -> TaskEventEnvelope:
    event_type = TaskEventType(record.event_type)
    payload_model = CORE_EVENT_PAYLOADS.get(event_type)
    payload = record.payload_json
    if payload_model is not None:
        try:
            payload = payload_model.model_validate(record.payload_json).model_dump(mode="python")
        except Exception:
            payload = record.payload_json
    return TaskEventEnvelope(
        event_id=record.event_id,
        event_type=event_type,
        event_level=record.event_level,
        visibility_scope=record.visibility_scope,
        sequence=record.event_seq,
        session_id=record.session_id,
        task_id=record.task_id,
        task_run_id=record.task_run_id,
        node_id=record.node_id,
        approval_id=record.approval_id,
        trace_id=record.trace_id,
        causation_event_id=record.causation_event_id,
        emitted_by=record.emitted_by,
        occurred_at=record.occurred_at,
        payload=payload,
    )


def build_run_snapshot(uow, task_run_id: str) -> RunSnapshotResponse:
    run = uow.task_runs.get(task_run_id)
    if run is None:
        raise ValueError(f"Task run not found: {task_run_id}")
    task = uow.tasks.get(run.task_id)
    if task is None:
        raise ValueError(f"Task not found for run: {task_run_id}")
    nodes = uow.task_nodes.list_by_run(task_run_id)
    current_nodes = [
        CurrentNodeSnapshot(
            node_id=node.node_id,
            title=node.title,
            status=node.status.value,
        )
        for node in nodes
        if node.status not in TERMINAL_NODE_STATUSES
    ]
    return RunSnapshotResponse(
        session_id=task.session_id,
        task_id=task.task_id,
        task_run_id=task_run_id,
        data=TaskRunSnapshotPayload(
            task_status=task.status.value,
            current_nodes=current_nodes,
            summary=run.summary_text,
        ),
    )
