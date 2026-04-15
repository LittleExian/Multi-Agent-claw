from __future__ import annotations

from src.runtime.contracts import DispatchOutcome, NodeExecutor
from src.runtime.langgraph_kernel import LangGraphRunKernel


class RunDispatcher:
    """Thin wrapper around the LangGraph-backed runtime kernel."""

    def __init__(
        self,
        uow_factory,
        *,
        orchestrator,
        executor: NodeExecutor,
    ):
        self.kernel = LangGraphRunKernel(
            uow_factory,
            orchestrator=orchestrator,
            executor=executor,
        )

    def dispatch_run(self, task_run_id: str, *, max_iterations: int = 20) -> DispatchOutcome:
        return self.kernel.invoke_run(task_run_id, max_iterations=max_iterations)

    def resume_run(
        self,
        task_run_id: str,
        *,
        resume_payload: dict | None = None,
        max_iterations: int = 20,
    ) -> DispatchOutcome:
        return self.kernel.resume_run(
            task_run_id,
            resume_payload=resume_payload,
            max_iterations=max_iterations,
        )
