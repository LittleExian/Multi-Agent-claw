from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import JSONDict, JSONList, MutableTimestampedSchema, SwarmSchema, TimestampedSchema
from .enums import (
    ActorType,
    ApprovalKind,
    ApprovalStatus,
    ArtifactDirection,
    ArtifactType,
    Complexity,
    EventLevel,
    LLMCallStatus,
    MemoryScope,
    MemorySourceType,
    MessageDirection,
    MessageRole,
    NodeStatus,
    NodeType,
    Priority,
    RiskLevel,
    SessionKind,
    SessionStatus,
    SkillCandidateStatus,
    SkillSourceScope,
    TaskRunStatus,
    TaskStatus,
    ToolCallStatus,
    ToolCategory,
    TriggerKind,
    VisibilityScope,
)


class SessionRecord(MutableTimestampedSchema):
    session_id: str
    channel: str
    user_id: str
    session_kind: SessionKind
    title: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    source_ref: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)
    last_message_at: datetime | None = None


class MessageRecord(TimestampedSchema):
    message_id: str
    session_id: str
    channel: str
    direction: MessageDirection
    role: MessageRole
    channel_message_id: str | None = None
    reply_to_message_id: str | None = None
    content_text: str | None = None
    content_json: JSONDict = Field(default_factory=dict)
    token_count: int | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)
    received_at: datetime | None = None


class MessageAttachmentRecord(TimestampedSchema):
    attachment_id: str
    message_id: str
    name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    storage_uri: str
    extracted_text_uri: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class SessionCompactionRecord(TimestampedSchema):
    compaction_id: str
    session_id: str
    summary_text: str
    files_touched_json: JSONList = Field(default_factory=list)
    decisions_json: JSONList = Field(default_factory=list)
    source_message_from: str | None = None
    source_message_to: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class TaskRecord(MutableTimestampedSchema):
    task_id: str
    session_id: str
    source_message_id: str | None = None
    title: str
    objective: str
    task_kind: str = "general"
    status: TaskStatus
    priority: Priority = Priority.NORMAL
    complexity: Complexity
    risk_level: RiskLevel = RiskLevel.READ
    current_run_id: str | None = None
    latest_run_id: str | None = None
    success_criteria_json: JSONList = Field(default_factory=list)
    constraints_json: JSONList = Field(default_factory=list)
    expected_outputs_json: JSONList = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    created_by: str
    completed_at: datetime | None = None


class TaskRunRecord(MutableTimestampedSchema):
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


class TaskNodeRecord(MutableTimestampedSchema):
    node_id: str
    task_run_id: str
    parent_node_id: str | None = None
    step_key: str
    node_type: NodeType
    role: str
    title: str
    goal: str
    status: NodeStatus
    order_index: int | None = None
    depth: int = 0
    approval_required: bool = False
    inputs_json: JSONList = Field(default_factory=list)
    outputs_json: JSONList = Field(default_factory=list)
    dependencies_json: JSONList = Field(default_factory=list)
    tools_hint_json: JSONList = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TaskNodeRunRecord(SwarmSchema):
    node_run_id: str
    node_id: str
    task_run_id: str
    attempt_no: int
    status: str
    model_profile: str | None = None
    agent_role: str
    input_context_json: JSONDict = Field(default_factory=dict)
    output_json: JSONDict | None = None
    error_json: JSONDict | None = None
    latency_ms: int | None = None
    started_at: datetime
    completed_at: datetime | None = None


class ApprovalRecord(SwarmSchema):
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
    requested_actions_json: JSONList = Field(default_factory=list)
    decision_json: JSONDict | None = None
    requested_by: str
    decided_by: str | None = None
    requested_at: datetime
    decided_at: datetime | None = None
    expires_at: datetime | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class ArtifactRecord(TimestampedSchema):
    artifact_id: str
    session_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    source_message_id: str | None = None
    artifact_type: ArtifactType
    direction: ArtifactDirection
    title: str | None = None
    mime_type: str | None = None
    storage_uri: str
    size_bytes: int | None = None
    sha256: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class TaskEventRecord(SwarmSchema):
    event_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    session_id: str
    node_id: str | None = None
    approval_id: str | None = None
    trace_id: str | None = None
    event_seq: int
    event_type: str
    event_level: EventLevel
    visibility_scope: VisibilityScope
    emitted_by: str
    causation_event_id: str | None = None
    payload_json: JSONDict = Field(default_factory=dict)
    occurred_at: datetime
    persisted_at: datetime


class LLMCallRecord(SwarmSchema):
    llm_call_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    node_run_id: str | None = None
    trace_id: str | None = None
    phase: str
    role: str | None = None
    model_profile: str
    provider: str
    endpoint: str | None = None
    supports_tools: bool = False
    request_tokens: int | None = None
    response_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    status: LLMCallStatus
    request_summary_json: JSONDict = Field(default_factory=dict)
    response_summary_json: JSONDict = Field(default_factory=dict)
    error_json: JSONDict | None = None
    started_at: datetime
    completed_at: datetime | None = None


class ToolCallRecord(SwarmSchema):
    tool_call_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    node_run_id: str | None = None
    approval_id: str | None = None
    trace_id: str | None = None
    tool_name: str
    tool_category: ToolCategory
    risk_level: RiskLevel
    preview_only: bool = False
    server_name: str | None = None
    arguments_json: JSONDict = Field(default_factory=dict)
    result_summary_json: JSONDict | None = None
    latency_ms: int | None = None
    status: ToolCallStatus
    error_json: JSONDict | None = None
    started_at: datetime
    completed_at: datetime | None = None


class SandboxRunRecord(SwarmSchema):
    sandbox_run_id: str
    tool_call_id: str
    profile_name: str
    image_name: str | None = None
    network_enabled: bool = False
    mounts_json: JSONList = Field(default_factory=list)
    command_text: str | None = None
    exit_code: int | None = None
    timed_out: bool = False
    stdout_excerpt: str | None = None
    stderr_excerpt: str | None = None
    started_at: datetime
    completed_at: datetime | None = None


class RunCheckpointRecord(TimestampedSchema):
    checkpoint_id: str
    task_run_id: str
    thread_id: str
    checkpoint_ns: str | None = None
    saver_backend: str
    saver_ref: str
    state_digest: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class AuditLogRecord(TimestampedSchema):
    audit_id: str
    session_id: str | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    node_id: str | None = None
    trace_id: str | None = None
    action_type: str
    actor_type: ActorType
    actor_id: str | None = None
    summary_text: str
    details_json: JSONDict = Field(default_factory=dict)


class MemoryEntryRecord(TimestampedSchema):
    memory_id: str
    session_id: str | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    scope: MemoryScope
    source_type: MemorySourceType
    title: str | None = None
    content_text: str
    summary_text: str | None = None
    embedding_ref: str | None = None
    tags_json: JSONList = Field(default_factory=list)
    importance: float = 0.5
    metadata_json: JSONDict = Field(default_factory=dict)


class SkillCandidateRecord(TimestampedSchema):
    skill_candidate_id: str
    source_task_id: str
    source_task_run_id: str | None = None
    name: str
    summary_text: str
    applicability_text: str | None = None
    plan_template_json: JSONDict
    tool_requirements_json: JSONList = Field(default_factory=list)
    status: SkillCandidateStatus
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class SkillCatalogSnapshotRecord(SwarmSchema):
    snapshot_id: str
    skill_name: str
    source_path: str
    source_scope: SkillSourceScope
    version_text: str | None = None
    sha256: str | None = None
    enabled: bool = True
    metadata_json: JSONDict = Field(default_factory=dict)
    loaded_at: datetime
