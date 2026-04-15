from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from src.shared.schemas.common import JSONDict, JSONList, SwarmSchema
from src.shared.schemas.enums import Complexity, RiskLevel


class InboundAttachment(SwarmSchema):
    name: str
    storage_uri: str
    mime_type: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    extracted_text_uri: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class InboundEnvelope(SwarmSchema):
    message_id: str
    session_id: str | None = None
    user_id: str
    channel: str
    content: str = ""
    attachments: list[InboundAttachment] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)
    received_at: datetime


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"


class IntakeDecisionKind(str, Enum):
    CHAT = "chat"
    NEW_TASK = "new_task"
    RESUME_TASK = "resume_task"
    APPROVAL_REPLY = "approval_reply"
    CLARIFICATION_REPLY = "clarification_reply"


class TaskDraft(SwarmSchema):
    session_id: str
    source_message_id: str
    user_id: str
    channel: str
    content: str
    attachments: list[InboundAttachment] = Field(default_factory=list)
    explicit_start: bool = False
    referenced_task_id: str | None = None
    metadata_json: JSONDict = Field(default_factory=dict)


class IntakeDecision(SwarmSchema):
    kind: IntakeDecisionKind
    session_id: str
    source_message_id: str
    task_id: str | None = None
    task_run_id: str | None = None
    approval_id: str | None = None
    approval_decision: ApprovalDecision | None = None
    draft: TaskDraft | None = None
    reason: str | None = None


class RiskProfile(SwarmSchema):
    requires_network: bool = False
    requires_file_write: bool = False
    requires_command_exec: bool = False
    requires_external_account: bool = False
    destructive_actions: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    risk_level: RiskLevel = RiskLevel.READ


class TaskSpec(SwarmSchema):
    task_id: str
    session_id: str
    source_message_id: str
    title: str
    objective: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    recommended_roles: list[str] = Field(default_factory=list)
    complexity: Complexity
    risk_profile: RiskProfile
    requires_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)


class PlanStep(SwarmSchema):
    step_id: str
    name: str
    role: str
    goal: str
    dependencies: list[str] = Field(default_factory=list)
    tools_hint: list[str] = Field(default_factory=list)
    approval_required: bool = False
    metadata_json: JSONDict = Field(default_factory=dict)


class ExecutionPlan(SwarmSchema):
    task_id: str
    task_run_id: str
    summary_strategy: str
    steps: list[PlanStep] = Field(default_factory=list)
    entry_steps: list[str] = Field(default_factory=list)
    exit_steps: list[str] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)


class TaskLifecycleResult(SwarmSchema):
    session_id: str
    intake_kind: IntakeDecisionKind | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    status: str
    approval_id: str | None = None
    requires_clarification: bool = False
    emitted_event_ids: list[str] = Field(default_factory=list)


class ApprovalResolutionPayload(SwarmSchema):
    approval_id: str
    decision: ApprovalDecision
    decided_by: str
    edited_actions: JSONList = Field(default_factory=list)
