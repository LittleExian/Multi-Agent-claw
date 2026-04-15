from __future__ import annotations

from src.runtime.contracts import DispatchOutcome
from src.runtime.dispatcher import RunDispatcher


class WorkerLoop:
    """Simple synchronous worker loop for the MVP runtime."""

    def __init__(self, uow_factory, *, dispatcher: RunDispatcher):
        self.uow_factory = uow_factory
        self.dispatcher = dispatcher

    def drain_run(self, task_run_id: str, *, max_cycles: int = 20) -> DispatchOutcome:
        return self.dispatcher.dispatch_run(task_run_id, max_iterations=max_cycles)

    def run_once(self, *, limit_runs: int = 20, max_cycles_per_run: int = 20) -> list[DispatchOutcome]:
        with self.uow_factory() as uow:
            run_ids = uow.task_nodes.list_runnable_run_ids(limit=limit_runs)
        return [
            self.dispatcher.dispatch_run(task_run_id, max_iterations=max_cycles_per_run)
            for task_run_id in run_ids
        ]
