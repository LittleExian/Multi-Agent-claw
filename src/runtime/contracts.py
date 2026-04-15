from __future__ import annotations

from typing import Protocol

from pydantic import Field

from src.shared.schemas import JSONDict, RiskLevel, SwarmSchema


class NodeExecutionContext(SwarmSchema):
    session_id: str
    task_id: str
    task_run_id: str
    node_id: str
    node_run_id: str
    attempt_no: int
    role: str
    title: str
    goal: str
    task_title: str
    objective: str
    success_criteria: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    tools_hint: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.READ
    task_metadata_json: JSONDict = Field(default_factory=dict)
    node_metadata_json: JSONDict = Field(default_factory=dict)
    spec_json: JSONDict = Field(default_factory=dict)
    plan_json: JSONDict = Field(default_factory=dict)


class NodeExecutionResult(SwarmSchema):
    output_summary: str
    output_json: JSONDict = Field(default_factory=dict)
    artifact_ids: list[str] = Field(default_factory=list)
    llm_call_ids: list[str] = Field(default_factory=list)
    tool_call_ids: list[str] = Field(default_factory=list)
    metadata_json: JSONDict = Field(default_factory=dict)


class NodeExecutor(Protocol):
    def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        """Execute a single runtime node."""


class DispatchOutcome(SwarmSchema):
    task_run_id: str
    processed_node_ids: list[str] = Field(default_factory=list)
    completed_node_ids: list[str] = Field(default_factory=list)
    failed_node_id: str | None = None
    paused_node_id: str | None = None
    approval_id: str | None = None
    final_run_status: str | None = None
    final_task_status: str | None = None
    idle_reason: str | None = None
    iterations: int = 0
    metadata_json: JSONDict = Field(default_factory=dict)
