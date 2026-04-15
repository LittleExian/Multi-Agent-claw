from __future__ import annotations

from src.shared.schemas import (
    ApprovalKind,
    ApprovalRecord,
    ApprovalStatus,
    EventLevel,
    NodeStatus,
    NodeType,
    RiskLevel,
    TaskEventType,
    TaskNodeRecord,
    TaskNodeRunRecord,
    TaskRunRecord,
    TaskRunStatus,
    TaskStatus,
    TriggerKind,
)

from .base import ServiceBase
from .models import (
    ApprovalDecision,
    ApprovalResolutionPayload,
    ExecutionPlan,
    PlanStep,
    TaskSpec,
)
from .utils import generate_prefixed_id, utc_now


class OrchestratorService(ServiceBase):
    def start_run(self, spec: TaskSpec) -> ExecutionPlan:
        now = utc_now()
        with self.uow_factory() as uow:
            task = uow.tasks.get(spec.task_id)
            if task is None:
                raise ValueError(f"Task not found: {spec.task_id}")

            task_run_id = generate_prefixed_id("run")
            run_no = uow.task_runs.next_run_no(spec.task_id)
            plan = self._build_plan(spec, task_run_id)
            run = TaskRunRecord(
                task_run_id=task_run_id,
                task_id=spec.task_id,
                thread_id=task_run_id,
                run_no=run_no,
                trigger_kind=TriggerKind.NEW if run_no == 1 else TriggerKind.RESUME,
                status=TaskRunStatus.RUNNING,
                spec_json=spec.model_dump(mode="python"),
                plan_json=plan.model_dump(mode="python"),
                context_snapshot_json={
                    "session_id": spec.session_id,
                    "source_message_id": spec.source_message_id,
                    "task_title": spec.title,
                    "objective": spec.objective,
                },
                created_at=now,
                updated_at=now,
                started_at=now,
            )
            uow.task_runs.insert(run)

            nodes = self._plan_to_nodes(plan, created_at=now)
            uow.task_nodes.insert_many(nodes)
            uow.tasks.set_current_run(
                spec.task_id,
                current_run_id=task_run_id,
                latest_run_id=task_run_id,
                status=TaskStatus.RUNNING,
                updated_at=now,
            )

            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_CREATED,
                session_id=spec.session_id,
                task_id=spec.task_id,
                task_run_id=task_run_id,
                emitted_by="orchestrator",
                payload_json={"run_no": run_no},
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_PLAN_READY,
                session_id=spec.session_id,
                task_id=spec.task_id,
                task_run_id=task_run_id,
                emitted_by="orchestrator",
                payload_json={
                    "summary_strategy": plan.summary_strategy,
                    "step_count": len(plan.steps),
                    "entry_steps": plan.entry_steps,
                    "exit_steps": plan.exit_steps,
                },
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_STARTED,
                session_id=spec.session_id,
                task_id=spec.task_id,
                task_run_id=task_run_id,
                emitted_by="orchestrator",
                payload_json={"status": TaskRunStatus.RUNNING.value},
            )
            for node in nodes:
                self._emit_event(
                    uow,
                    event_type=TaskEventType.NODE_CREATED,
                    session_id=spec.session_id,
                    task_id=spec.task_id,
                    task_run_id=task_run_id,
                    node_id=node.node_id,
                    emitted_by="orchestrator",
                    payload_json={
                        "title": node.title,
                        "role": node.role,
                        "status": node.status.value,
                    },
                )
                if node.status == NodeStatus.READY:
                    self._emit_event(
                        uow,
                        event_type=TaskEventType.NODE_READY,
                        session_id=spec.session_id,
                        task_id=spec.task_id,
                        task_run_id=task_run_id,
                        node_id=node.node_id,
                        emitted_by="orchestrator",
                        payload_json={
                            "title": node.title,
                            "dependencies": node.dependencies_json,
                        },
                    )
            return plan

    def start_node_attempt(
        self,
        *,
        task_run_id: str,
        node_id: str,
        model_profile: str | None = None,
    ) -> TaskNodeRunRecord:
        now = utc_now()
        with self.uow_factory() as uow:
            node = uow.task_nodes.get(node_id)
            if node is None:
                raise ValueError(f"Node not found: {node_id}")
            if node.task_run_id != task_run_id:
                raise ValueError("Node does not belong to the provided task run")
            attempts = uow.task_node_runs.list_by_node(node_id)
            node_run = TaskNodeRunRecord(
                node_run_id=generate_prefixed_id("nrun"),
                node_id=node_id,
                task_run_id=task_run_id,
                attempt_no=len(attempts) + 1,
                status="running",
                model_profile=model_profile,
                agent_role=node.role,
                input_context_json={
                    "goal": node.goal,
                    "tools_hint": node.tools_hint_json,
                },
                started_at=now,
            )
            uow.task_node_runs.insert(node_run)
            uow.task_nodes.update_status(node_id, NodeStatus.RUNNING, now, started_at=now)

            run = uow.task_runs.get(task_run_id)
            task = uow.tasks.get(run.task_id) if run else None
            if run is None or task is None:
                raise ValueError(f"Task run not found: {task_run_id}")

            self._emit_event(
                uow,
                event_type=TaskEventType.NODE_STARTED,
                session_id=task.session_id,
                task_id=run.task_id,
                task_run_id=task_run_id,
                node_id=node_id,
                emitted_by="orchestrator",
                payload_json={
                    "role": node.role,
                    "title": node.title,
                    "goal": node.goal,
                    "attempt_no": node_run.attempt_no,
                },
            )
            return node_run

    def complete_node_attempt(
        self,
        *,
        node_run_id: str,
        output_json: dict,
        output_summary: str,
        artifact_ids: list[str] | None = None,
        llm_call_ids: list[str] | None = None,
        tool_call_ids: list[str] | None = None,
    ) -> None:
        now = utc_now()
        with self.uow_factory() as uow:
            node_run = uow.task_node_runs.get(node_run_id)
            if node_run is None:
                raise ValueError(f"Node run not found: {node_run_id}")
            node = uow.task_nodes.get(node_run.node_id)
            run = uow.task_runs.get(node_run.task_run_id)
            task = uow.tasks.get(run.task_id) if run else None
            if node is None or run is None or task is None:
                raise ValueError("Node or task run not found for node completion")

            uow.task_node_runs.update_fields(
                node_run_id,
                {
                    "status": "completed",
                    "output_json": output_json,
                    "latency_ms": self._latency_ms(node_run.started_at, now),
                    "completed_at": now,
                },
            )
            uow.task_nodes.update_status(node.node_id, NodeStatus.COMPLETED, now, completed_at=now)

            self._emit_event(
                uow,
                event_type=TaskEventType.NODE_COMPLETED,
                session_id=task.session_id,
                task_id=run.task_id,
                task_run_id=run.task_run_id,
                node_id=node.node_id,
                emitted_by="orchestrator",
                payload_json={
                    "attempt_no": node_run.attempt_no,
                    "output_summary": output_summary,
                    "artifact_ids": artifact_ids or [],
                    "llm_call_ids": llm_call_ids or [],
                    "tool_call_ids": tool_call_ids or [],
                },
            )
            self._unlock_ready_nodes_locked(
                uow,
                task_run_id=run.task_run_id,
                session_id=task.session_id,
                task_id=task.task_id,
            )

            remaining = [
                item
                for item in uow.task_nodes.list_by_run(run.task_run_id)
                if item.status not in {NodeStatus.COMPLETED, NodeStatus.SKIPPED, NodeStatus.CANCELLED}
            ]
            if not remaining:
                self._complete_run_locked(uow, run.task_run_id)

    def fail_node_attempt(
        self,
        *,
        node_run_id: str,
        error_code: str,
        error_message: str,
        retryable: bool,
    ) -> None:
        now = utc_now()
        with self.uow_factory() as uow:
            node_run = uow.task_node_runs.get(node_run_id)
            if node_run is None:
                raise ValueError(f"Node run not found: {node_run_id}")
            node = uow.task_nodes.get(node_run.node_id)
            run = uow.task_runs.get(node_run.task_run_id)
            task = uow.tasks.get(run.task_id) if run else None
            if node is None or run is None or task is None:
                raise ValueError("Node, task run, or task not found for node failure")

            uow.task_node_runs.update_fields(
                node_run_id,
                {
                    "status": "failed",
                    "error_json": {
                        "error_code": error_code,
                        "error_message": error_message,
                        "retryable": retryable,
                    },
                    "latency_ms": self._latency_ms(node_run.started_at, now),
                    "completed_at": now,
                },
            )
            uow.task_nodes.update_status(node.node_id, NodeStatus.FAILED, now, completed_at=now)
            uow.task_runs.update_status(
                run.task_run_id,
                TaskRunStatus.FAILED,
                now,
                completed_at=now,
                error_json={"error_code": error_code, "error_message": error_message},
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_FAILED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=run.task_run_id,
                emitted_by="orchestrator",
                event_level=EventLevel.ERROR,
                payload_json={
                    "failed_node_id": node.node_id,
                    "error_code": error_code,
                    "error_message": error_message,
                },
            )
            uow.tasks.set_current_run(
                task.task_id,
                current_run_id=None,
                latest_run_id=run.task_run_id,
                status=TaskStatus.FAILED,
                updated_at=now,
                completed_at=now,
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.NODE_FAILED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=run.task_run_id,
                node_id=node.node_id,
                emitted_by="orchestrator",
                event_level=EventLevel.ERROR,
                payload_json={
                    "attempt_no": node_run.attempt_no,
                    "error_code": error_code,
                    "error_message": error_message,
                    "retryable": retryable,
                },
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.TASK_FAILED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=run.task_run_id,
                emitted_by="orchestrator",
                event_level=EventLevel.ERROR,
                payload_json={
                    "summary_text": error_message,
                    "failed_node_ids": [node.node_id],
                    "last_error_code": error_code,
                    "recoverable": retryable,
                },
            )

    def request_approval(
        self,
        *,
        task_run_id: str,
        node_id: str,
        approval_kind: ApprovalKind,
        title: str,
        summary_text: str,
        risk_level: RiskLevel,
        requested_by: str,
        requested_actions: list[dict],
        preview_json: dict | None = None,
        expires_at=None,
    ) -> ApprovalRecord:
        now = utc_now()
        with self.uow_factory() as uow:
            run = uow.task_runs.get(task_run_id)
            node = uow.task_nodes.get(node_id)
            task = uow.tasks.get(run.task_id) if run else None
            if run is None or node is None or task is None:
                raise ValueError("Task run, node, or task not found for approval request")

            approval = ApprovalRecord(
                approval_id=generate_prefixed_id("app"),
                task_id=task.task_id,
                task_run_id=task_run_id,
                node_id=node_id,
                approval_kind=approval_kind,
                status=ApprovalStatus.PENDING,
                risk_level=risk_level,
                title=title,
                summary_text=summary_text,
                preview_json=preview_json or {},
                requested_actions_json=requested_actions,
                requested_by=requested_by,
                requested_at=now,
                expires_at=expires_at,
            )
            uow.approvals.insert(approval)
            uow.task_nodes.update_status(node_id, NodeStatus.AWAITING_APPROVAL, now)
            uow.task_runs.update_status(task_run_id, TaskRunStatus.PAUSED, now)
            uow.tasks.set_current_run(
                task.task_id,
                current_run_id=task_run_id,
                latest_run_id=task_run_id,
                status=TaskStatus.AWAITING_APPROVAL,
                updated_at=now,
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.TASK_APPROVAL_REQUESTED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=task_run_id,
                node_id=node_id,
                approval_id=approval.approval_id,
                emitted_by="orchestrator",
                payload_json={
                    "approval_id": approval.approval_id,
                    "approval_kind": approval_kind.value,
                    "title": title,
                    "summary": summary_text,
                    "risk_level": risk_level,
                    "actions": requested_actions,
                    "expires_at": expires_at,
                },
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_PAUSED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=task_run_id,
                emitted_by="orchestrator",
                payload_json={"approval_id": approval.approval_id, "reason": "awaiting_approval"},
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.NODE_AWAITING_APPROVAL,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=task_run_id,
                node_id=node_id,
                approval_id=approval.approval_id,
                emitted_by="orchestrator",
                payload_json={"approval_id": approval.approval_id},
            )
            return approval

    def resolve_approval(self, payload: ApprovalResolutionPayload) -> ApprovalRecord:
        now = utc_now()
        with self.uow_factory() as uow:
            approval = uow.approvals.get(payload.approval_id)
            if approval is None:
                raise ValueError(f"Approval not found: {payload.approval_id}")
            run = uow.task_runs.get(approval.task_run_id)
            task = uow.tasks.get(approval.task_id)
            node = uow.task_nodes.get(approval.node_id) if approval.node_id else None
            if run is None or task is None:
                raise ValueError("Task or run not found for approval resolution")

            status_map = {
                ApprovalDecision.APPROVE: ApprovalStatus.APPROVED,
                ApprovalDecision.REJECT: ApprovalStatus.REJECTED,
                ApprovalDecision.EDIT: ApprovalStatus.EDITED,
            }
            resolved_status = status_map[payload.decision]
            decision_json = (
                {"edited_actions": payload.edited_actions}
                if payload.decision == ApprovalDecision.EDIT
                else {"decision": payload.decision.value}
            )
            uow.approvals.resolve(
                approval.approval_id,
                status=resolved_status,
                decided_by=payload.decided_by,
                decided_at=now,
                decision_json=decision_json,
            )

            if payload.decision in {ApprovalDecision.APPROVE, ApprovalDecision.EDIT}:
                if node:
                    uow.task_nodes.update_status(node.node_id, NodeStatus.READY, now)
                uow.task_runs.update_status(run.task_run_id, TaskRunStatus.RUNNING, now)
                uow.tasks.set_current_run(
                    task.task_id,
                    current_run_id=run.task_run_id,
                    latest_run_id=run.task_run_id,
                    status=TaskStatus.RUNNING,
                    updated_at=now,
                )
                resolved_event = TaskEventType.TASK_APPROVAL_RESOLVED
                self._emit_event(
                    uow,
                    event_type=resolved_event,
                    session_id=task.session_id,
                    task_id=task.task_id,
                    task_run_id=run.task_run_id,
                    node_id=node.node_id if node else None,
                    approval_id=approval.approval_id,
                    emitted_by="orchestrator",
                    payload_json={"decision": payload.decision.value},
                )
                if node:
                    self._emit_event(
                        uow,
                        event_type=TaskEventType.NODE_READY,
                        session_id=task.session_id,
                        task_id=task.task_id,
                        task_run_id=run.task_run_id,
                        node_id=node.node_id,
                        approval_id=approval.approval_id,
                        emitted_by="orchestrator",
                        payload_json={"reason": "approval_resolved"},
                    )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.RUN_RESUMED,
                    session_id=task.session_id,
                    task_id=task.task_id,
                    task_run_id=run.task_run_id,
                    emitted_by="orchestrator",
                    payload_json={"approval_id": approval.approval_id},
                )
            else:
                if node:
                    uow.task_nodes.update_status(node.node_id, NodeStatus.BLOCKED, now)
                uow.task_runs.update_status(run.task_run_id, TaskRunStatus.BLOCKED, now)
                uow.tasks.set_current_run(
                    task.task_id,
                    current_run_id=run.task_run_id,
                    latest_run_id=run.task_run_id,
                    status=TaskStatus.BLOCKED,
                    updated_at=now,
                )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_APPROVAL_RESOLVED,
                    session_id=task.session_id,
                    task_id=task.task_id,
                    task_run_id=run.task_run_id,
                    node_id=node.node_id if node else None,
                    approval_id=approval.approval_id,
                    emitted_by="orchestrator",
                    payload_json={"decision": payload.decision.value},
                )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.RUN_BLOCKED,
                    session_id=task.session_id,
                    task_id=task.task_id,
                    task_run_id=run.task_run_id,
                    emitted_by="orchestrator",
                    payload_json={"approval_id": approval.approval_id},
                )

            return uow.approvals.get(approval.approval_id)  # type: ignore[return-value]

    def cancel_run(self, task_run_id: str, cancelled_by: str) -> None:
        now = utc_now()
        with self.uow_factory() as uow:
            run = uow.task_runs.get(task_run_id)
            if run is None:
                raise ValueError(f"Task run not found: {task_run_id}")
            task = uow.tasks.get(run.task_id)
            if task is None:
                raise ValueError(f"Task not found: {run.task_id}")

            uow.task_runs.update_status(run.task_run_id, TaskRunStatus.CANCELLED, now, completed_at=now)
            uow.tasks.set_current_run(
                task.task_id,
                current_run_id=None,
                latest_run_id=run.task_run_id,
                status=TaskStatus.CANCELLED,
                updated_at=now,
                completed_at=now,
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.RUN_CANCELLED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=run.task_run_id,
                emitted_by="orchestrator",
                payload_json={"cancelled_by": cancelled_by},
            )
            self._emit_event(
                uow,
                event_type=TaskEventType.TASK_CANCELLED,
                session_id=task.session_id,
                task_id=task.task_id,
                task_run_id=run.task_run_id,
                emitted_by="orchestrator",
                payload_json={"cancelled_by": cancelled_by},
            )

    def _complete_run_locked(self, uow, task_run_id: str) -> None:
        now = utc_now()
        run = uow.task_runs.get(task_run_id)
        if run is None:
            raise ValueError(f"Task run not found: {task_run_id}")
        task = uow.tasks.get(run.task_id)
        if task is None:
            raise ValueError(f"Task not found: {run.task_id}")

        uow.task_runs.update_status(
            task_run_id,
            TaskRunStatus.COMPLETED,
            now,
            completed_at=now,
            summary_text="Run completed successfully.",
        )
        uow.tasks.set_current_run(
            task.task_id,
            current_run_id=None,
            latest_run_id=task_run_id,
            status=TaskStatus.COMPLETED,
            updated_at=now,
            completed_at=now,
        )
        all_nodes = uow.task_nodes.list_by_run(task_run_id)
        success_nodes = [node for node in all_nodes if node.status == NodeStatus.COMPLETED]
        failed_nodes = [node for node in all_nodes if node.status == NodeStatus.FAILED]
        self._emit_event(
            uow,
            event_type=TaskEventType.RUN_COMPLETED,
            session_id=task.session_id,
            task_id=task.task_id,
            task_run_id=task_run_id,
            emitted_by="orchestrator",
            payload_json={"status": TaskRunStatus.COMPLETED.value},
        )
        self._emit_event(
            uow,
            event_type=TaskEventType.TASK_COMPLETED,
            session_id=task.session_id,
            task_id=task.task_id,
            task_run_id=task_run_id,
            emitted_by="orchestrator",
            payload_json={
                "summary_text": "任务已完成。",
                "output_artifact_ids": [],
                "node_count": len(all_nodes),
                "success_node_count": len(success_nodes),
                "failed_node_count": len(failed_nodes),
            },
        )

    def _unlock_ready_nodes_locked(
        self,
        uow,
        *,
        task_run_id: str,
        session_id: str,
        task_id: str,
    ) -> list[str]:
        now = utc_now()
        nodes = uow.task_nodes.list_by_run(task_run_id)
        completed_steps = {node.step_key for node in nodes if node.status == NodeStatus.COMPLETED}
        unlocked: list[str] = []
        for node in nodes:
            if node.status != NodeStatus.PENDING:
                continue
            dependencies = [str(dep) for dep in node.dependencies_json]
            if all(step_id in completed_steps for step_id in dependencies):
                uow.task_nodes.update_status(node.node_id, NodeStatus.READY, now)
                unlocked.append(node.node_id)
                self._emit_event(
                    uow,
                    event_type=TaskEventType.NODE_READY,
                    session_id=session_id,
                    task_id=task_id,
                    task_run_id=task_run_id,
                    node_id=node.node_id,
                    emitted_by="orchestrator",
                    payload_json={"dependencies": dependencies},
                )
        return unlocked

    def _build_plan(self, spec: TaskSpec, task_run_id: str) -> ExecutionPlan:
        worker_roles = [
            role
            for role in spec.recommended_roles
            if role not in {"writer", "coordinator"}
        ]
        if not worker_roles:
            worker_roles = ["coordinator"]

        steps: list[PlanStep] = []
        for idx, role in enumerate(worker_roles[:2], start=1):
            step_id = f"step_{idx}"
            steps.append(
                PlanStep(
                    step_id=step_id,
                    name=f"{role}_step_{idx}",
                    role=role,
                    goal=spec.objective,
                    dependencies=[],
                    tools_hint=self._tools_for_role(
                        role,
                        risk_level=spec.risk_profile.risk_level,
                        requires_command_exec=spec.risk_profile.requires_command_exec,
                        requires_file_write=spec.risk_profile.requires_file_write,
                    ),
                    approval_required=spec.risk_profile.risk_level != RiskLevel.READ and role == "coder",
                )
            )

        if "writer" in spec.recommended_roles and steps:
            steps.append(
                PlanStep(
                    step_id=f"step_{len(steps)+1}",
                    name="writer_summary",
                    role="writer",
                    goal=f"根据前序结果生成最终输出：{', '.join(spec.expected_outputs)}",
                    dependencies=[step.step_id for step in steps],
                    tools_hint=[],
                    approval_required=False,
                )
            )

        if not steps:
            steps.append(
                PlanStep(
                    step_id="step_1",
                    name="coordinator_step",
                    role="coordinator",
                    goal=spec.objective,
                )
            )

        return ExecutionPlan(
            task_id=spec.task_id,
            task_run_id=task_run_id,
            summary_strategy="merge_and_summarize",
            steps=steps,
            entry_steps=[step.step_id for step in steps if not step.dependencies],
            exit_steps=[steps[-1].step_id],
        )

    def _plan_to_nodes(self, plan: ExecutionPlan, *, created_at) -> list[TaskNodeRecord]:
        entry_steps = set(plan.entry_steps)
        nodes: list[TaskNodeRecord] = []
        for idx, step in enumerate(plan.steps, start=1):
            nodes.append(
                TaskNodeRecord(
                    node_id=generate_prefixed_id("node"),
                    task_run_id=plan.task_run_id,
                    parent_node_id=None,
                    step_key=step.step_id,
                    node_type=NodeType.WORKER if step.role != "writer" else NodeType.SUMMARY,
                    role=step.role,
                    title=step.name,
                    goal=step.goal,
                    status=NodeStatus.READY if step.step_id in entry_steps else NodeStatus.PENDING,
                    order_index=idx,
                    approval_required=step.approval_required,
                    dependencies_json=step.dependencies,
                    tools_hint_json=step.tools_hint,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )
        return nodes

    @staticmethod
    def _tools_for_role(
        role: str,
        *,
        risk_level: RiskLevel,
        requires_command_exec: bool,
        requires_file_write: bool,
    ) -> list[str]:
        if role == "coder":
            tools = [
                "filesystem.list_dir",
                "filesystem.read_file",
            ]
            if requires_file_write:
                tools.append("filesystem.write_file")
            if requires_command_exec:
                tools.append("shell.exec")
            return tools
        if role == "researcher":
            return ["browser.search", "browser.fetch"]
        if role == "browser":
            return ["browser.search", "browser.fetch"]
        if role == "writer":
            return []
        return []

    @staticmethod
    def _latency_ms(started_at, finished_at) -> int:
        return max(int((finished_at - started_at).total_seconds() * 1000), 0)
