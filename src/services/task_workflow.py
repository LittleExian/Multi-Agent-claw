from __future__ import annotations

from .models import (
    ApprovalResolutionPayload,
    InboundEnvelope,
    IntakeDecision,
    IntakeDecisionKind,
    TaskLifecycleResult,
)
from .orchestrator import OrchestratorService
from .task_analyzer import TaskAnalyzerService
from .task_intake import TaskIntakeService


class TaskWorkflowService:
    """Coordinates intake, analysis, and orchestration for the primary task lifecycle."""

    def __init__(self, uow_factory):
        self.uow_factory = uow_factory
        self.intake = TaskIntakeService(uow_factory)
        self.analyzer = TaskAnalyzerService(uow_factory)
        self.orchestrator = OrchestratorService(uow_factory)

    def process_inbound(self, envelope: InboundEnvelope) -> TaskLifecycleResult:
        decision = self.intake.handle_inbound(envelope)
        return self.advance_from_intake(decision, decided_by=envelope.user_id)

    def advance_from_intake(
        self,
        decision: IntakeDecision,
        *,
        decided_by: str | None = None,
    ) -> TaskLifecycleResult:
        if decision.kind == IntakeDecisionKind.CHAT:
            return TaskLifecycleResult(
                session_id=decision.session_id,
                intake_kind=decision.kind,
                status="chat",
            )

        if decision.kind == IntakeDecisionKind.APPROVAL_REPLY:
            if decision.approval_id is None or decision.approval_decision is None:
                raise ValueError("approval_reply decision requires approval_id and approval_decision")
            approval = self.orchestrator.resolve_approval(
                ApprovalResolutionPayload(
                    approval_id=decision.approval_id,
                    decision=decision.approval_decision,
                    decided_by=decided_by or "user",
                )
            )
            status = "running" if approval.status.value in {"approved", "edited"} else "blocked"
            return TaskLifecycleResult(
                session_id=decision.session_id,
                intake_kind=decision.kind,
                task_id=approval.task_id,
                task_run_id=approval.task_run_id,
                status=status,
                approval_id=approval.approval_id,
            )

        spec = self.analyzer.analyze(decision)
        if spec.requires_clarification:
            return TaskLifecycleResult(
                session_id=spec.session_id,
                intake_kind=decision.kind,
                task_id=spec.task_id,
                status="needs_clarification",
                requires_clarification=True,
            )

        plan = self.orchestrator.start_run(spec)
        return TaskLifecycleResult(
            session_id=spec.session_id,
            intake_kind=decision.kind,
            task_id=spec.task_id,
            task_run_id=plan.task_run_id,
            status="running",
        )
