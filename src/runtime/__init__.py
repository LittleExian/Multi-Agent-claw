from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "DefaultNodeExecutor",
    "DispatchOutcome",
    "LangGraphCheckpointerHandle",
    "LangGraphRunKernel",
    "LLMToolNodeExecutor",
    "NodeExecutionContext",
    "NodeExecutionError",
    "NodeExecutionResult",
    "NodeExecutor",
    "RunDispatcher",
    "WorkerLoop",
    "build_sqlite_checkpointer",
]

if TYPE_CHECKING:
    from .checkpoints import LangGraphCheckpointerHandle
    from .contracts import DispatchOutcome, NodeExecutionContext, NodeExecutionResult, NodeExecutor
    from .dispatcher import RunDispatcher
    from .executor import DefaultNodeExecutor, NodeExecutionError
    from .langgraph_kernel import LangGraphRunKernel
    from .llm_executor import LLMToolNodeExecutor
    from .worker_loop import WorkerLoop


def __getattr__(name: str) -> Any:
    if name in {"LangGraphCheckpointerHandle", "build_sqlite_checkpointer"}:
        from .checkpoints import LangGraphCheckpointerHandle, build_sqlite_checkpointer

        return {
            "LangGraphCheckpointerHandle": LangGraphCheckpointerHandle,
            "build_sqlite_checkpointer": build_sqlite_checkpointer,
        }[name]
    if name in {"DispatchOutcome", "NodeExecutionContext", "NodeExecutionResult", "NodeExecutor"}:
        from .contracts import DispatchOutcome, NodeExecutionContext, NodeExecutionResult, NodeExecutor

        return {
            "DispatchOutcome": DispatchOutcome,
            "NodeExecutionContext": NodeExecutionContext,
            "NodeExecutionResult": NodeExecutionResult,
            "NodeExecutor": NodeExecutor,
        }[name]
    if name in {"DefaultNodeExecutor", "NodeExecutionError"}:
        from .executor import DefaultNodeExecutor, NodeExecutionError

        return {
            "DefaultNodeExecutor": DefaultNodeExecutor,
            "NodeExecutionError": NodeExecutionError,
        }[name]
    if name == "RunDispatcher":
        from .dispatcher import RunDispatcher

        return RunDispatcher
    if name == "WorkerLoop":
        from .worker_loop import WorkerLoop

        return WorkerLoop
    if name == "LLMToolNodeExecutor":
        from .llm_executor import LLMToolNodeExecutor

        return LLMToolNodeExecutor
    if name == "LangGraphRunKernel":
        from .langgraph_kernel import LangGraphRunKernel

        return LangGraphRunKernel
    raise AttributeError(f"module 'src.runtime' has no attribute {name!r}")
