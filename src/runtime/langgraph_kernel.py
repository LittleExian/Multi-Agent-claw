from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from src.runtime.contracts import DispatchOutcome, NodeExecutionContext, NodeExecutor
from src.runtime.executor import NodeExecutionError
from src.shared.schemas import (
    ApprovalKind,
    ApprovalStatus,
    EventLevel,
    NodeStatus,
    RiskLevel,
    TaskEventRecord,
    TaskEventType,
    TaskRunStatus,
    VisibilityScope,
)


class RunGraphState(TypedDict, total=False):
    task_run_id: str
    max_iterations: int
    iterations: int
    processed_node_ids: list[str]
    completed_node_ids: list[str]
    failed_node_id: str | None
    paused_node_id: str | None
    approval_id: str | None
    final_run_status: str | None
    final_task_status: str | None
    idle_reason: str | None
    metadata_json: dict[str, Any]
    next_action: str


class LangGraphRunKernel:
    """LangGraph-backed runtime loop for a single task run."""

    INTERRUPTS_KEY = "__interrupt__"

    def __init__(
        self,
        uow_factory,
        *,
        orchestrator,
        executor: NodeExecutor,
    ):
        self.uow_factory = uow_factory
        self.orchestrator = orchestrator
        self.executor = executor
        self._graph = self._compile_graph()

    def invoke_run(self, task_run_id: str, *, max_iterations: int = 20) -> DispatchOutcome:
        initial_state = self._initial_state(task_run_id, max_iterations=max_iterations)
        return self._invoke(
            task_run_id,
            initial_state,
            max_iterations=max_iterations,
        )

    def resume_run(
        self,
        task_run_id: str,
        *,
        resume_payload: Mapping[str, Any] | None = None,
        max_iterations: int = 20,
    ) -> DispatchOutcome:
        config = self._thread_config(task_run_id)
        snapshot = self._graph.get_state(config)
        if not snapshot.interrupts:
            return self.invoke_run(task_run_id, max_iterations=max_iterations)
        return self._invoke(
            task_run_id,
            Command(resume=dict(resume_payload or {})),
            max_iterations=max_iterations,
        )

    def _compile_graph(self):
        builder = StateGraph(RunGraphState)
        builder.add_node("tick", self._tick)
        builder.add_edge(START, "tick")
        builder.add_conditional_edges(
            "tick",
            self._route_after_tick,
            {
                "tick": "tick",
                "end": END,
            },
        )
        return builder.compile(checkpointer=InMemorySaver())

    def _route_after_tick(self, state: RunGraphState) -> str:
        if state.get("next_action") == "tick":
            return "tick"
        return "end"

    def _tick(self, state: RunGraphState) -> RunGraphState:
        task_run_id = str(state["task_run_id"])
        max_iterations = int(state.get("max_iterations", 20))
        iterations = int(state.get("iterations", 0))
        outcome = self._state_to_outcome(task_run_id, state)

        if iterations >= max_iterations:
            final_run_status, final_task_status = self._load_final_statuses(task_run_id)
            return {
                **self._outcome_to_state(outcome),
                "final_run_status": final_run_status,
                "final_task_status": final_task_status,
                "idle_reason": "max_iterations_reached",
                "next_action": "end",
            }

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
                return {
                    **self._outcome_to_state(outcome),
                    "iterations": iterations,
                    "next_action": "end",
                }

            ready_nodes = uow.task_nodes.list_by_status(task_run_id, NodeStatus.READY)
            if not ready_nodes:
                outcome.idle_reason = "no_ready_nodes"
                return {
                    **self._outcome_to_state(outcome),
                    "iterations": iterations,
                    "next_action": "end",
                }

            node = ready_nodes[0]
            latest_approval = uow.approvals.latest_for_node(node.node_id)
            requires_approval = node.approval_required and not (
                latest_approval is not None
                and latest_approval.task_run_id == task_run_id
                and latest_approval.status in {ApprovalStatus.APPROVED, ApprovalStatus.EDITED}
            )
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
            approval_id = latest_approval.approval_id if latest_approval is not None else None
            if latest_approval is None or latest_approval.status != ApprovalStatus.PENDING:
                approval = self.orchestrator.request_approval(
                    task_run_id=task_run_id,
                    node_id=node.node_id,
                    approval_kind=self._approval_kind_for(context_payload.risk_level),
                    title=f"确认执行节点：{node.title}",
                    summary_text=f"节点 '{node.title}' 需要审批后才能继续执行。",
                    risk_level=context_payload.risk_level,
                    requested_by="langgraph_runtime",
                    requested_actions=self._requested_actions(context_payload),
                    preview_json={
                        "goal": node.goal,
                        "tools_hint": list(node.tools_hint_json),
                    },
                )
                approval_id = approval.approval_id
            interrupt(
                {
                    "reason": "approval_requested",
                    "approval_id": approval_id,
                    "node_id": node.node_id,
                    "task_run_id": task_run_id,
                }
            )
            return {}

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
            return {
                **self._outcome_to_state(outcome),
                "iterations": iterations + 1,
                "next_action": "end",
            }

        final_run_status, final_task_status = self._load_final_statuses(task_run_id)
        outcome.final_run_status = final_run_status
        outcome.final_task_status = final_task_status

        if iterations + 1 >= max_iterations:
            outcome.idle_reason = "max_iterations_reached"
            return {
                **self._outcome_to_state(outcome),
                "iterations": iterations + 1,
                "next_action": "end",
            }

        if final_run_status == TaskRunStatus.RUNNING.value and self._has_ready_nodes(task_run_id):
            return {
                **self._outcome_to_state(outcome),
                "iterations": iterations + 1,
                "idle_reason": None,
                "next_action": "tick",
            }

        if final_run_status == TaskRunStatus.COMPLETED.value:
            outcome.idle_reason = "run_completed"
        elif final_run_status == TaskRunStatus.PAUSED.value:
            outcome.idle_reason = "approval_pending"
        else:
            outcome.idle_reason = "no_ready_nodes"
        return {
            **self._outcome_to_state(outcome),
            "iterations": iterations + 1,
            "next_action": "end",
        }

    def _invoke(
        self,
        task_run_id: str,
        payload: RunGraphState | Command,
        *,
        max_iterations: int,
    ) -> DispatchOutcome:
        config = self._thread_config(task_run_id)
        try:
            result = self._graph.invoke(payload, config=config)
        finally:
            self._touch_checkpoint(task_run_id)

        if isinstance(result, dict) and self.INTERRUPTS_KEY in result:
            snapshot = self._graph.get_state(config)
            outcome = self._outcome_from_interrupt(
                task_run_id,
                snapshot.values,
                result[self.INTERRUPTS_KEY],
            )
            outcome.iterations = int(snapshot.values.get("iterations", 0)) + 1
            final_run_status, final_task_status = self._load_final_statuses(task_run_id)
            outcome.final_run_status = final_run_status
            outcome.final_task_status = final_task_status
            return outcome

        return self._state_to_outcome(task_run_id, result)

    def _initial_state(self, task_run_id: str, *, max_iterations: int) -> RunGraphState:
        return {
            "task_run_id": task_run_id,
            "max_iterations": max_iterations,
            "iterations": 0,
            "processed_node_ids": [],
            "completed_node_ids": [],
            "failed_node_id": None,
            "paused_node_id": None,
            "approval_id": None,
            "final_run_status": None,
            "final_task_status": None,
            "idle_reason": None,
            "metadata_json": {},
            "next_action": "tick",
        }

    def _thread_config(self, task_run_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": task_run_id}}

    def _outcome_from_interrupt(
        self,
        task_run_id: str,
        values: Mapping[str, Any],
        interrupts: Any,
    ) -> DispatchOutcome:
        outcome = self._state_to_outcome(task_run_id, values)
        interrupt_payload: Mapping[str, Any] = {}
        if isinstance(interrupts, list) and interrupts:
            candidate = interrupts[0]
            interrupt_payload = getattr(candidate, "value", {}) or {}
        if isinstance(interrupt_payload, Mapping):
            outcome.approval_id = self._string_or_none(interrupt_payload.get("approval_id"))
            outcome.paused_node_id = self._string_or_none(interrupt_payload.get("node_id"))
            outcome.idle_reason = str(interrupt_payload.get("reason") or "approval_requested")
            outcome.metadata_json = {
                **outcome.metadata_json,
                "interrupt_payload": dict(interrupt_payload),
            }
        return outcome

    def _state_to_outcome(self, task_run_id: str, state: Mapping[str, Any] | None) -> DispatchOutcome:
        state = state or {}
        return DispatchOutcome(
            task_run_id=task_run_id,
            processed_node_ids=[str(item) for item in state.get("processed_node_ids", [])],
            completed_node_ids=[str(item) for item in state.get("completed_node_ids", [])],
            failed_node_id=self._string_or_none(state.get("failed_node_id")),
            paused_node_id=self._string_or_none(state.get("paused_node_id")),
            approval_id=self._string_or_none(state.get("approval_id")),
            final_run_status=self._string_or_none(state.get("final_run_status")),
            final_task_status=self._string_or_none(state.get("final_task_status")),
            idle_reason=self._string_or_none(state.get("idle_reason")),
            iterations=int(state.get("iterations", 0) or 0),
            metadata_json=dict(state.get("metadata_json", {})),
        )

    def _outcome_to_state(self, outcome: DispatchOutcome) -> RunGraphState:
        return {
            "task_run_id": outcome.task_run_id,
            "processed_node_ids": list(outcome.processed_node_ids),
            "completed_node_ids": list(outcome.completed_node_ids),
            "failed_node_id": outcome.failed_node_id,
            "paused_node_id": outcome.paused_node_id,
            "approval_id": outcome.approval_id,
            "final_run_status": outcome.final_run_status,
            "final_task_status": outcome.final_task_status,
            "idle_reason": outcome.idle_reason,
            "metadata_json": dict(outcome.metadata_json),
        }

    def _touch_checkpoint(self, task_run_id: str) -> None:
        now = self._utc_now()
        with self.uow_factory() as uow:
            run = uow.task_runs.get(task_run_id)
            if run is None:
                return
            uow.task_runs.update_status(
                task_run_id,
                run.status,
                now,
                last_checkpoint_at=now,
            )

    def _load_final_statuses(self, task_run_id: str) -> tuple[str | None, str | None]:
        with self.uow_factory() as uow:
            run = uow.task_runs.get(task_run_id)
            task = uow.tasks.get(run.task_id) if run is not None else None
            return (
                run.status.value if run is not None else None,
                task.status.value if task is not None else None,
            )

    def _has_ready_nodes(self, task_run_id: str) -> bool:
        with self.uow_factory() as uow:
            return bool(uow.task_nodes.list_by_status(task_run_id, NodeStatus.READY))

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
                emitted_by="langgraph_runtime",
                event_level=EventLevel.INFO,
                payload_json={
                    "message": message,
                    "progress_percent": progress_percent,
                    "recent_artifact_ids": [],
                },
            )

    def _emit_event(
        self,
        uow,
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
        now = self._utc_now()
        event = TaskEventRecord(
            event_id=self._generate_prefixed_id("evt"),
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

    @staticmethod
    def _approval_kind_for(risk_level: RiskLevel) -> ApprovalKind:
        if risk_level == RiskLevel.DESTRUCTIVE:
            return ApprovalKind.DESTRUCTIVE_TOOL
        if risk_level == RiskLevel.MUTABLE:
            return ApprovalKind.MUTABLE_TOOL
        return ApprovalKind.PLAN_CONFIRMATION

    @staticmethod
    def _requested_actions(context: NodeExecutionContext) -> list[dict[str, str]]:
        return [
            {
                "tool": tool_name,
                "action": "execute",
                "goal": context.goal,
            }
            for tool_name in context.tools_hint
        ] or [{"tool": "runtime.execute_node", "action": "execute", "goal": context.goal}]

    @staticmethod
    def _string_or_none(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _generate_prefixed_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:12]}"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
