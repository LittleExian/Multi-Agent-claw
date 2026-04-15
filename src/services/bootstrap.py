from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.application.events import InMemoryEventBus
from src.llm import LLMRuntimeConfig, OpenAICompatibleClient
from src.runtime import (
    DefaultNodeExecutor,
    LangGraphCheckpointerHandle,
    LLMToolNodeExecutor,
    NodeExecutor,
    RunDispatcher,
    WorkerLoop,
    build_sqlite_checkpointer,
)
from src.storage import SQLiteDatabase, initialize_database
from src.tools import LocalSandboxExecutor, ToolRegistry

from .orchestrator import OrchestratorService
from .task_analyzer import TaskAnalyzerService
from .task_intake import TaskIntakeService
from .task_workflow import TaskWorkflowService
from .uow import SQLiteUnitOfWork, build_uow_factory


@dataclass(slots=True)
class ServiceContainer:
    db: SQLiteDatabase
    uow_factory: Callable[[], SQLiteUnitOfWork]
    event_bus: InMemoryEventBus
    checkpointer: LangGraphCheckpointerHandle
    llm_config: LLMRuntimeConfig
    llm_client: OpenAICompatibleClient
    sandbox_executor: LocalSandboxExecutor
    tool_registry: ToolRegistry
    fallback_node_executor: DefaultNodeExecutor
    node_executor: NodeExecutor
    run_dispatcher: RunDispatcher
    worker_loop: WorkerLoop
    task_intake: TaskIntakeService
    task_analyzer: TaskAnalyzerService
    orchestrator: OrchestratorService
    task_workflow: TaskWorkflowService


def build_service_container(
    db: SQLiteDatabase | str | Path,
    *,
    initialize: bool = True,
    checkpoint_db_path: str | Path | None = None,
    event_bus: InMemoryEventBus | None = None,
    llm_config: LLMRuntimeConfig | None = None,
    llm_client: OpenAICompatibleClient | None = None,
    sandbox_executor: LocalSandboxExecutor | None = None,
    tool_registry: ToolRegistry | None = None,
) -> ServiceContainer:
    database = db if isinstance(db, SQLiteDatabase) else SQLiteDatabase(db)
    if initialize:
        initialize_database(database)
    resolved_checkpoint_db_path = _resolve_checkpoint_db_path(database.db_path, configured=checkpoint_db_path)
    checkpointer = build_sqlite_checkpointer(resolved_checkpoint_db_path)
    try:
        resolved_llm_config = llm_config or (
            llm_client.config if llm_client is not None else LLMRuntimeConfig.from_env()
        )
        resolved_llm_client = llm_client or OpenAICompatibleClient(resolved_llm_config)
        resolved_sandbox_executor = sandbox_executor or LocalSandboxExecutor(
            workspace_root=resolved_llm_config.workspace_root,
            default_timeout_seconds=resolved_llm_config.shell_timeout_seconds,
            default_network_enabled=resolved_llm_config.shell_network_enabled,
        )
        resolved_tool_registry = tool_registry
        if resolved_tool_registry is None:
            resolved_tool_registry = ToolRegistry(
                workspace_root=resolved_llm_config.workspace_root,
                sandbox_executor=resolved_sandbox_executor,
                browser_timeout_seconds=resolved_llm_config.browser_timeout_seconds,
                max_read_chars=resolved_llm_config.max_read_chars,
            )
        else:
            resolved_sandbox_executor = resolved_tool_registry.sandbox_executor
        resolved_event_bus = event_bus or InMemoryEventBus()
        uow_factory = build_uow_factory(
            database,
            event_publisher=resolved_event_bus.publish,
        )
        fallback_node_executor = DefaultNodeExecutor()
        node_executor = LLMToolNodeExecutor(
            uow_factory,
            llm_client=resolved_llm_client,
            tool_registry=resolved_tool_registry,
            fallback_executor=fallback_node_executor,
            max_rounds=resolved_llm_config.max_tool_rounds,
        )
        orchestrator = OrchestratorService(uow_factory)
        run_dispatcher = RunDispatcher(
            uow_factory,
            orchestrator=orchestrator,
            executor=node_executor,
            checkpointer=checkpointer.checkpointer,
        )
        worker_loop = WorkerLoop(
            uow_factory,
            dispatcher=run_dispatcher,
        )
        return ServiceContainer(
            db=database,
            uow_factory=uow_factory,
            event_bus=resolved_event_bus,
            checkpointer=checkpointer,
            llm_config=resolved_llm_config,
            llm_client=resolved_llm_client,
            sandbox_executor=resolved_sandbox_executor,
            tool_registry=resolved_tool_registry,
            fallback_node_executor=fallback_node_executor,
            node_executor=node_executor,
            run_dispatcher=run_dispatcher,
            worker_loop=worker_loop,
            task_intake=TaskIntakeService(uow_factory),
            task_analyzer=TaskAnalyzerService(uow_factory),
            orchestrator=orchestrator,
            task_workflow=TaskWorkflowService(uow_factory),
        )
    except Exception:
        checkpointer.close()
        raise


def _resolve_checkpoint_db_path(
    db_path: str | Path,
    *,
    configured: str | Path | None = None,
) -> Path:
    if configured is not None:
        return Path(configured).expanduser().resolve()

    env_path = os.getenv("SWARM_CHECKPOINT_DB_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    resolved = Path(db_path).expanduser().resolve()
    return resolved.with_name(f"{resolved.stem}.checkpoints.sqlite3")
