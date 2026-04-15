from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.services.models import ApprovalDecision, TaskLifecycleResult
from src.shared.schemas import (
    JSONDict,
    ApprovalKind,
    ApprovalStatus,
    ArtifactDirection,
    ArtifactType,
    Complexity,
    CurrentNodeSnapshot,
    EventLevel,
    NodeStatus,
    Priority,
    RiskLevel,
    SessionKind,
    SessionStatus,
    SwarmSchema,
    TaskEventEnvelope,
    TaskRunSnapshotPayload,
    TaskRunStatus,
    TaskStatus,
    TriggerKind,
)


class HealthResponse(SwarmSchema):
    status: str
    db_path: str
    schema_version: str


class GatewayAttachmentInput(SwarmSchema):
    name: str
    storage_uri: str
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    extracted_text_uri: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class GatewayMessageRequest(SwarmSchema):
    message_id: str | None = None
    session_id: str | None = None
    user_id: str
    channel: str
    content: str = ""
    attachments: list[GatewayAttachmentInput] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    received_at: datetime | None = None


class SessionRead(SwarmSchema):
    session_id: str
    channel: str
    user_id: str
    session_kind: SessionKind
    title: str | None = None
    status: SessionStatus
    source_ref: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


class ArtifactRead(SwarmSchema):
    artifact_id: str
    artifact_type: ArtifactType
    direction: ArtifactDirection
    title: str | None = None
    mime_type: str | None = None
    storage_uri: str
    size_bytes: int | None = None
    sha256: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)
    created_at: datetime


class TaskNodeRead(SwarmSchema):
    node_id: str
    step_key: str
    role: str
    title: str
    goal: str
    status: NodeStatus
    order_index: int | None = None
    depth: int = 0
    approval_required: bool = False
    dependencies: list[str] = Field(default_factory=list)
    tools_hint: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class TaskRunRead(SwarmSchema):
    task_run_id: str
    task_id: str
    thread_id: str
    run_no: int
    trigger_kind: TriggerKind
    status: TaskRunStatus
    spec_json: JSONDict
    plan_json: JSONDict | None = None
    context_snapshot_json: JSONDict = Field(default_factory=dict)
    summary_text: str | None = None
    error_json: JSONDict | None = None
    queue_wait_ms: int | None = None
    approval_wait_ms: int | None = None
    checkpoint_backend: str | None = None
    checkpoint_ref: str | None = None
    last_checkpoint_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    nodes: list[TaskNodeRead] = Field(default_factory=list)
    artifacts: list[ArtifactRead] = Field(default_factory=list)


class TaskRead(SwarmSchema):
    task_id: str
    session_id: str
    source_message_id: str | None = None
    title: str
    objective: str
    task_kind: str
    status: TaskStatus
    priority: Priority
    complexity: Complexity
    risk_level: RiskLevel
    current_run_id: str | None = None
    latest_run_id: str | None = None
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    created_by: str
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    current_run: TaskRunRead | None = None
    latest_run: TaskRunRead | None = None


class ApprovalRead(SwarmSchema):
    approval_id: str
    task_id: str
    task_run_id: str
    node_id: str | None = None
    approval_kind: ApprovalKind
    status: ApprovalStatus
    risk_level: RiskLevel
    title: str
    summary_text: str
    preview_json: JSONDict = Field(default_factory=dict)
    requested_actions_json: list[JSONDict] = Field(default_factory=list)
    decision_json: JSONDict | None = None
    requested_by: str
    decided_by: str | None = None
    requested_at: datetime
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class GatewayMessageResponse(SwarmSchema):
    message_id: str
    session: SessionRead
    result: TaskLifecycleResult
    task: TaskRead | None = None
    run: TaskRunRead | None = None
    approval: ApprovalRead | None = None


class TaskListResponse(SwarmSchema):
    items: list[TaskRead] = Field(default_factory=list)


class TaskDetailResponse(SwarmSchema):
    task: TaskRead


class TaskRunListResponse(SwarmSchema):
    items: list[TaskRunRead] = Field(default_factory=list)


class TaskRunDetailResponse(SwarmSchema):
    run: TaskRunRead


class ApprovalListResponse(SwarmSchema):
    items: list[ApprovalRead] = Field(default_factory=list)


class ApprovalDetailResponse(SwarmSchema):
    approval: ApprovalRead


class ApprovalResolveRequest(SwarmSchema):
    decision: ApprovalDecision
    decided_by: str
    edited_actions: list[JSONDict] = Field(default_factory=list)


class ApprovalResolveResponse(SwarmSchema):
    approval: ApprovalRead
    result: TaskLifecycleResult


class EventListResponse(SwarmSchema):
    session_id: str | None = None
    task_run_id: str | None = None
    after_seq: int | None = None
    next_cursor: int | None = None
    items: list[TaskEventEnvelope] = Field(default_factory=list)


class RunSnapshotResponse(SwarmSchema):
    session_id: str
    task_id: str
    task_run_id: str
    data: TaskRunSnapshotPayload


class RunEventStreamQuery(SwarmSchema):
    cursor: int = 0
    include_snapshot: bool = True
    poll_interval_ms: int = 1000
    heartbeat_interval_ms: int = 15000


class EventStreamState(SwarmSchema):
    cursor: int
    session_id: str
    task_run_id: str
    event_level: EventLevel = EventLevel.INFO
    current_nodes: list[CurrentNodeSnapshot] = Field(default_factory=list)
