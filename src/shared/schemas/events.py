from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .common import JSONDict, JSONList, SCHEMA_VERSION, SwarmSchema
from .enums import EventLevel, TaskEventType, VisibilityScope, WebSocketMessageType


class ToolActionSpec(SwarmSchema):
    tool_name: str
    arguments: JSONDict = Field(default_factory=dict)


class TaskCreatedPayload(SwarmSchema):
    title: str
    objective: str
    complexity: str
    risk_level: str
    source_message_id: str | None = None


class TaskClarificationRequestedPayload(SwarmSchema):
    questions: list[str]
    blocking_fields: list[str]


class TaskApprovalRequestedPayload(SwarmSchema):
    approval_id: str
    approval_kind: str
    title: str
    summary: str
    risk_level: str
    actions: list[ToolActionSpec] = Field(default_factory=list)
    expires_at: datetime | None = None


class RunPlanReadyPayload(SwarmSchema):
    summary_strategy: str
    step_count: int
    entry_steps: list[str] = Field(default_factory=list)
    exit_steps: list[str] = Field(default_factory=list)


class NodeStartedPayload(SwarmSchema):
    role: str
    title: str
    goal: str
    attempt_no: int


class NodeProgressPayload(SwarmSchema):
    message: str
    progress_percent: int | None = None
    recent_artifact_ids: list[str] = Field(default_factory=list)


class NodeCompletedPayload(SwarmSchema):
    attempt_no: int
    output_summary: str
    artifact_ids: list[str] = Field(default_factory=list)
    llm_call_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)


class NodeFailedPayload(SwarmSchema):
    attempt_no: int
    error_code: str
    error_message: str
    retryable: bool


class TaskCompletedPayload(SwarmSchema):
    summary_text: str
    output_artifact_ids: list[str] = Field(default_factory=list)
    node_count: int
    success_node_count: int
    failed_node_count: int


class TaskFailedPayload(SwarmSchema):
    summary_text: str
    failed_node_ids: list[str] = Field(default_factory=list)
    last_error_code: str | None = None
    recoverable: bool = False


class TaskEventEnvelope(SwarmSchema):
    schema_version: str = SCHEMA_VERSION
    event_id: str
    event_type: TaskEventType
    event_level: EventLevel
    visibility_scope: VisibilityScope
    sequence: int
    session_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    approval_id: str | None = None
    trace_id: str | None = None
    causation_event_id: str | None = None
    emitted_by: str
    occurred_at: datetime
    payload: JSONDict = Field(default_factory=dict)


class CurrentNodeSnapshot(SwarmSchema):
    node_id: str
    title: str
    status: str


class TaskRunSnapshotPayload(SwarmSchema):
    task_status: str
    current_nodes: list[CurrentNodeSnapshot] = Field(default_factory=list)
    summary: str | None = None


class WebSocketEventMessage(SwarmSchema):
    type: Literal[WebSocketMessageType.EVENT] = WebSocketMessageType.EVENT
    cursor: int
    session_id: str
    task_run_id: str
    data: TaskEventEnvelope


class WebSocketSnapshotMessage(SwarmSchema):
    type: Literal[WebSocketMessageType.SNAPSHOT] = WebSocketMessageType.SNAPSHOT
    cursor: int
    session_id: str
    task_run_id: str
    data: TaskRunSnapshotPayload


class WebSocketAckMessage(SwarmSchema):
    type: Literal[WebSocketMessageType.ACK] = WebSocketMessageType.ACK
    cursor: int
    session_id: str
    task_run_id: str
    data: JSONDict = Field(default_factory=dict)


class WebSocketErrorPayload(SwarmSchema):
    code: str
    message: str
    details: JSONDict = Field(default_factory=dict)


class WebSocketErrorMessage(SwarmSchema):
    type: Literal[WebSocketMessageType.ERROR] = WebSocketMessageType.ERROR
    cursor: int | None = None
    session_id: str | None = None
    task_run_id: str | None = None
    data: WebSocketErrorPayload


class WebSocketHeartbeatPayload(SwarmSchema):
    server_time: datetime


class WebSocketHeartbeatMessage(SwarmSchema):
    type: Literal[WebSocketMessageType.HEARTBEAT] = WebSocketMessageType.HEARTBEAT
    cursor: int | None = None
    session_id: str | None = None
    task_run_id: str | None = None
    data: WebSocketHeartbeatPayload


WebSocketMessage = (
    WebSocketEventMessage
    | WebSocketSnapshotMessage
    | WebSocketAckMessage
    | WebSocketErrorMessage
    | WebSocketHeartbeatMessage
)


CORE_EVENT_PAYLOADS: dict[TaskEventType, type[SwarmSchema]] = {
    TaskEventType.TASK_CREATED: TaskCreatedPayload,
    TaskEventType.TASK_CLARIFICATION_REQUESTED: TaskClarificationRequestedPayload,
    TaskEventType.TASK_APPROVAL_REQUESTED: TaskApprovalRequestedPayload,
    TaskEventType.RUN_PLAN_READY: RunPlanReadyPayload,
    TaskEventType.NODE_STARTED: NodeStartedPayload,
    TaskEventType.NODE_PROGRESS: NodeProgressPayload,
    TaskEventType.NODE_COMPLETED: NodeCompletedPayload,
    TaskEventType.NODE_FAILED: NodeFailedPayload,
    TaskEventType.TASK_COMPLETED: TaskCompletedPayload,
    TaskEventType.TASK_FAILED: TaskFailedPayload,
}
