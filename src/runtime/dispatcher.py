from __future__ import annotations

from src.runtime.contracts import DispatchOutcome, NodeExecutionContext, NodeExecutor
from src.runtime.executor import NodeExecutionError
from src.services.base import ServiceBase
from src.services.orchestrator import OrchestratorService
from src.shared.schemas import (
    ApprovalKind,
    ApprovalStatus,
    EventLevel,
    NodeStatus,
    RiskLevel,
    TaskEventType,
    TaskRunStatus,
)


class RunDispatcher(ServiceBase):
    """Consumes ready nodes and drives a run forward until it becomes idle."""

    def __init__(
        self,
        uow_factory,
        *,
        orchestrator: OrchestratorService,
        executor: NodeExecutor,
    ):
        super().__init__(uow_factory)
        self.orchestrator = orchestrator
        self.executor = executor

    def dispatch_run(self, task_run_id: str, *, max_iterations: int = 20) -> DispatchOutcome:
        outcome = DispatchOutcome(task_run_id=task_run_id)
        for iteration in range(max_iterations):
            outcome.iterations = iteration + 1
            with self.uow_factory() as uow:
                run = uow.task_runs.get(task_run_id)
                if run is None:
                    raise ValueError(f"Task run not found: {task_run_id}")
                task = uow.tasks.get(run.task_id)
                if task is None:
                    raise ValueError(f"Task not found for run: {task_run_id}")

                outcome.final_run_status = run.status.value
                outcome.final_task_status = task.status.value
                if run.status != TaskRunStatus.RUNNING:
                    outcome.idle_reason = f"run_not_runnable:{run.status.value}"
                    return outcome

                ready_nodes = uow.task_nodes.list_by_status(task_run_id, NodeStatus.READY)
                if not ready_nodes:
                    outcome.idle_reason = "no_ready_nodes"
                    return outcome

                node = ready_nodes[0]
                latest_approval = uow.approvals.latest_for_node(node.node_id)
                requires_approval = node.approval_required and not (
                    latest_approval is not None
                    and latest_approval.task_run_id == task_run_id
                    and latest_approval.status in {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}
                )
                if latest_approval is not None and latest_approval.status == ApprovalStatus.PENDING:
                    outcome.approval_id = latest_approval.approval_id
                    outcome.paused_node_id = node.node_id
                    outcome.final_run_status = run.status.value
                    outcome.final_task_status = task.status.value
                    outcome.idle_reason = "approval_pending"
                    return outcome

                context_payload = NodeExecutionContext(
                    session_id=task.session_id,
                    task_id=task.task_id,
                    task_run_id=run.task_run_id,
                    node_id=node.node_id,
                    node_run_id="",
                    attempt_no=0,
                    role=node.role,
                    title=node.title,
                    goal=node.goal,
                    task_title=task.title,
                    objective=task.objective,
                    success_criteria=list(task.success_criteria_json),
                    constraints=list(task.constraints_json),
                    expected_outputs=list(task.expected_outputs_json),
                    tools_hint=list(node.tools_hint_json),
                    risk_level=task.risk_level,
                    task_metadata_json=task.metadata_json,
                    node_metadata_json=node.metadata_json,
                    spec_json=run.spec_json,
                    plan_json=run.plan_json or {},
                )

            if requires_approval:
                approval = self.orchestrator.request_approval(
                    task_run_id=task_run_id,
                    node_id=node.node_id,
                    approval_kind=self._approval_kind_for(context_payload.risk_level),
                    title=f"确认执行节点：{node.title}",
                    summary_text=f"节点 '{node.title}' 需要审批后才能继续执行。",
                    risk_level=context_payload.risk_level,
                    requested_by="run_dispatcher",
                    requested_actions=self._requested_actions(context_payload),
                    preview_json={
                        "goal": node.goal,
                        "tools_hint": list(node.tools_hint_json),
                    },
                )
                outcome.approval_id = approval.approval_id
                outcome.paused_node_id = node.node_id
                outcome.final_run_status = "paused"
                outcome.final_task_status = "awaiting_approval"
                outcome.idle_reason = "approval_requested"
                return outcome

            node_run = self.orchestrator.start_node_attempt(
                task_run_id=task_run_id,
                node_id=node.node_id,
                model_profile="default_runtime",
            )
            execution_context = context_payload.model_copy(
                update={
                    "node_run_id": node_run.node_run_id,
                    "attempt_no": node_run.attempt_no,
                }
            )
            self._emit_progress(
                session_id=execution_context.session_id,
                task_id=execution_context.task_id,
                task_run_id=execution_context.task_run_id,
                node_id=execution_context.node_id,
                message=f"runtime 正在执行节点 {execution_context.title}",
                progress_percent=50,
            )

            try:
                result = self.executor.execute(execution_context)
                self.orchestrator.complete_node_attempt(
                    node_run_id=node_run.node_run_id,
                    output_json=result.output_json,
                    output_summary=result.output_summary,
                    artifact_ids=result.artifact_ids,
                    llm_call_ids=result.llm_call_ids,
                    tool_call_ids=result.tool_call_ids,
                )
                outcome.processed_node_ids.append(node.node_id)
                outcome.completed_node_ids.append(node.node_id)
            except NodeExecutionError as exc:
                self.orchestrator.fail_node_attempt(
                    node_run_id=node_run.node_run_id,
                    error_code=exc.error_code,
                    error_message=exc.error_message,
                    retryable=exc.retryable,
                )
                outcome.processed_node_ids.append(node.node_id)
                outcome.failed_node_id = node.node_id
                outcome.final_run_status = "failed"
                outcome.final_task_status = "failed"
                outcome.idle_reason = "node_failed"
                return outcome

        with self.uow_factory() as uow:
            run = uow.task_runs.get(task_run_id)
            task = uow.tasks.get(run.task_id) if run else None
            if run is not None:
                outcome.final_run_status = run.status.value
            if task is not None:
                outcome.final_task_status = task.status.value
        outcome.idle_reason = "max_iterations_reached"
        return outcome

    def _emit_progress(
        self,
        *,
        session_id: str,
        task_id: str,
        task_run_id: str,
        node_id: str,
        message: str,
        progress_percent: int,
    ) -> None:
        with self.uow_factory() as uow:
            self._emit_event(
                uow,
                event_type=TaskEventType.NODE_PROGRESS,
                session_id=session_id,
                task_id=task_id,
                task_run_id=task_run_id,
                node_id=node_id,
                emitted_by="run_dispatcher",
                event_level=EventLevel.INFO,
                payload_json={
                    "message": message,
                    "progress_percent": progress_percent,
                    "recent_artifact_ids": [],
                },
            )

    @staticmethod
    def _approval_kind_for(risk_level: RiskLevel) -> ApprovalKind:
        if risk_level == RiskLevel.DESTRUCTIVE:
            return ApprovalKind.DESTRUCTIVE_TOOL
        if risk_level == RiskLevel.MUTABLE:
            return ApprovalKind.MUTABLE_TOOL
        return ApprovalKind.PLAN_CONFIRMATION

    @staticmethod
    def _requested_actions(context: NodeExecutionContext) -> list[dict]:
        return [
            {
                "tool": tool_name,
                "action": "execute",
                "goal": context.goal,
            }
            for tool_name in context.tools_hint
        ] or [{"tool": "runtime.execute_node", "action": "execute", "goal": context.goal}]
