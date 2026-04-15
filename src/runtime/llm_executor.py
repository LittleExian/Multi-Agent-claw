from __future__ import annotations

import json
from typing import Any

from src.llm import ChatTurnResult, ModelProfile, OpenAICompatibleClient
from src.runtime.contracts import NodeExecutionContext, NodeExecutionResult
from src.runtime.executor import DefaultNodeExecutor, NodeExecutionError
from src.services.base import ServiceBase
from src.services.utils import compact_text, generate_prefixed_id, utc_now
from src.shared.schemas import (
    EventLevel,
    LLMCallRecord,
    LLMCallStatus,
    RiskLevel,
    SandboxRunRecord,
    TaskEventType,
    ToolCallRecord,
    ToolCallStatus,
    ToolCategory,
)
from src.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionError,
    ToolExecutionResult,
    ToolRegistry,
)


class LLMToolNodeExecutor(ServiceBase):
    """Node executor backed by an OpenAI-compatible chat-completions runtime."""

    def __init__(
        self,
        uow_factory,
        *,
        llm_client: OpenAICompatibleClient,
        tool_registry: ToolRegistry,
        fallback_executor: DefaultNodeExecutor | None = None,
        max_rounds: int = 6,
    ):
        super().__init__(uow_factory)
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.fallback_executor = fallback_executor or DefaultNodeExecutor()
        self.max_rounds = max_rounds

    def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        if not self.llm_client.is_configured():
            return self.fallback_executor.execute(context)
        profile = self.llm_client.config.resolve_profile()
        if profile is None:
            return self.fallback_executor.execute(context)
        return self._execute_with_llm(context, profile)

    def _execute_with_llm(
        self,
        context: NodeExecutionContext,
        profile: ModelProfile,
    ) -> NodeExecutionResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(context)},
            {"role": "user", "content": self._user_prompt(context)},
        ]
        tools = self.tool_registry.list_openai_tools(context.tools_hint) if profile.supports_tools else []
        llm_call_ids: list[str] = []
        tool_call_ids: list[str] = []
        artifact_ids: list[str] = []

        for round_index in range(self.max_rounds):
            started_at = utc_now()
            try:
                response = self.llm_client.complete(
                    messages=messages,
                    tools=tools,
                    profile_name=profile.name,
                )
                llm_call_id = self._record_llm_success(
                    context,
                    profile=profile,
                    response=response,
                    started_at=started_at,
                    request_messages=messages,
                    tools=tools,
                )
                llm_call_ids.append(llm_call_id)
            except Exception as exc:
                self._record_llm_failure(
                    context,
                    profile=profile,
                    error=exc,
                    started_at=started_at,
                    request_messages=messages,
                    tools=tools,
                )
                raise NodeExecutionError(
                    "llm.request_failed",
                    f"LLM request failed: {exc}",
                    retryable=True,
                ) from exc

            if response.tool_calls:
                messages.append(response.raw_assistant_message)
                for tool_call in response.tool_calls:
                    tool_result = self._execute_tool_call(
                        context,
                        tool_name=tool_call.name,
                        arguments_json=tool_call.arguments_json,
                    )
                    tool_call_ids.append(tool_result["tool_call_id"])
                    artifact_ids.extend(tool_result["artifact_ids"])
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": tool_result["content"],
                        }
                    )
                continue

            final_text = (response.content or "").strip() or "模型未返回正文，已完成本节点。"
            return NodeExecutionResult(
                output_summary=compact_text(final_text, 180),
                output_json={
                    "assistant_text": final_text,
                    "model": response.model,
                    "rounds": round_index + 1,
                    "tools_used": tool_call_ids,
                },
                artifact_ids=artifact_ids,
                llm_call_ids=llm_call_ids,
                tool_call_ids=tool_call_ids,
                metadata_json={
                    "executor": "llm_tool_runtime",
                    "model_profile": profile.name,
                    "provider": profile.provider,
                },
            )

        raise NodeExecutionError(
            "llm.max_rounds_exceeded",
            "LLM exceeded the maximum number of tool rounds without producing a final answer.",
            retryable=False,
        )

    def _execute_tool_call(
        self,
        context: NodeExecutionContext,
        *,
        tool_name: str,
        arguments_json: dict[str, Any],
    ) -> dict[str, Any]:
        tool_call_id = generate_prefixed_id("tool")
        started_at = utc_now()
        try:
            descriptor = self.tool_registry.get_descriptor(tool_name)
        except ToolExecutionError:
            descriptor = self._fallback_descriptor(tool_name)

        with self.uow_factory() as uow:
            self._emit_event(
                uow,
                event_type=TaskEventType.TOOL_CALLED,
                session_id=context.session_id,
                task_id=context.task_id,
                task_run_id=context.task_run_id,
                node_id=context.node_id,
                emitted_by="llm_tool_executor",
                event_level=EventLevel.INFO,
                trace_id=context.node_run_id,
                payload_json={
                    "tool_call_id": tool_call_id,
                    "tool_name": tool_name,
                    "arguments": arguments_json,
                },
            )

        execution_context = ToolExecutionContext(
            node=context,
            workspace_root=self.tool_registry.workspace_root.as_posix(),
        )
        try:
            result = self.tool_registry.execute(tool_name, arguments_json, execution_context)
        except ToolExecutionError as exc:
            return self._record_tool_failure(
                context,
                descriptor=descriptor,
                tool_call_id=tool_call_id,
                arguments_json=arguments_json,
                error=exc,
                started_at=started_at,
            )

        return self._record_tool_success(
            context,
            descriptor=descriptor,
            tool_call_id=tool_call_id,
            arguments_json=arguments_json,
            result=result,
            started_at=started_at,
        )

    def _record_tool_success(
        self,
        context: NodeExecutionContext,
        *,
        descriptor: ToolDescriptor,
        tool_call_id: str,
        arguments_json: dict[str, Any],
        result: ToolExecutionResult,
        started_at,
    ) -> dict[str, Any]:
        completed_at = utc_now()
        with self.uow_factory() as uow:
            uow.tool_calls.insert(
                ToolCallRecord(
                    tool_call_id=tool_call_id,
                    task_id=context.task_id,
                    task_run_id=context.task_run_id,
                    node_id=context.node_id,
                    node_run_id=context.node_run_id,
                    approval_id=None,
                    trace_id=context.node_run_id,
                    tool_name=descriptor.name,
                    tool_category=descriptor.category,
                    risk_level=descriptor.risk_level,
                    preview_only=False,
                    server_name=descriptor.server_name,
                    arguments_json=arguments_json,
                    result_summary_json={
                        "summary_text": result.summary_text,
                        "structured_content": result.structured_content,
                    },
                    latency_ms=max(int((completed_at - started_at).total_seconds() * 1000), 0),
                    status=ToolCallStatus.SUCCESS,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
            if result.sandbox_result is not None:
                uow.sandbox_runs.insert(
                    self._sandbox_run_record(
                        tool_call_id=tool_call_id,
                        sandbox_result=result.sandbox_result,
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                )
            self._emit_event(
                uow,
                event_type=TaskEventType.TOOL_COMPLETED,
                session_id=context.session_id,
                task_id=context.task_id,
                task_run_id=context.task_run_id,
                node_id=context.node_id,
                emitted_by="llm_tool_executor",
                trace_id=context.node_run_id,
                payload_json={
                    "tool_call_id": tool_call_id,
                    "tool_name": descriptor.name,
                    "summary_text": result.summary_text,
                },
            )
        return {
            "tool_call_id": tool_call_id,
            "artifact_ids": result.artifact_ids,
            "content": json.dumps(
                {
                    "ok": True,
                    "summary_text": result.summary_text,
                    "content": result.content_text,
                    "structured_content": result.structured_content,
                },
                ensure_ascii=False,
            ),
        }

    def _record_tool_failure(
        self,
        context: NodeExecutionContext,
        *,
        descriptor: ToolDescriptor,
        tool_call_id: str,
        arguments_json: dict[str, Any],
        error: ToolExecutionError,
        started_at,
    ) -> dict[str, Any]:
        completed_at = utc_now()
        with self.uow_factory() as uow:
            uow.tool_calls.insert(
                ToolCallRecord(
                    tool_call_id=tool_call_id,
                    task_id=context.task_id,
                    task_run_id=context.task_run_id,
                    node_id=context.node_id,
                    node_run_id=context.node_run_id,
                    approval_id=None,
                    trace_id=context.node_run_id,
                    tool_name=descriptor.name,
                    tool_category=descriptor.category,
                    risk_level=descriptor.risk_level,
                    preview_only=False,
                    server_name=descriptor.server_name,
                    arguments_json=arguments_json,
                    result_summary_json=None,
                    latency_ms=max(int((completed_at - started_at).total_seconds() * 1000), 0),
                    status=ToolCallStatus.TIMEOUT if error.timeout else ToolCallStatus.ERROR,
                    error_json={"code": error.code, "message": error.message},
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
            if error.sandbox_result is not None:
                uow.sandbox_runs.insert(
                    self._sandbox_run_record(
                        tool_call_id=tool_call_id,
                        sandbox_result=error.sandbox_result,
                        started_at=started_at,
                        completed_at=completed_at,
                    )
                )
            self._emit_event(
                uow,
                event_type=TaskEventType.TOOL_FAILED,
                session_id=context.session_id,
                task_id=context.task_id,
                task_run_id=context.task_run_id,
                node_id=context.node_id,
                emitted_by="llm_tool_executor",
                event_level=EventLevel.ERROR,
                trace_id=context.node_run_id,
                payload_json={
                    "tool_call_id": tool_call_id,
                    "tool_name": descriptor.name,
                    "error_code": error.code,
                    "error_message": error.message,
                },
            )
        return {
            "tool_call_id": tool_call_id,
            "artifact_ids": [],
            "content": json.dumps(
                {
                    "ok": False,
                    "error": {"code": error.code, "message": error.message},
                },
                ensure_ascii=False,
            ),
        }

    def _record_llm_success(
        self,
        context: NodeExecutionContext,
        *,
        profile: ModelProfile,
        response: ChatTurnResult,
        started_at,
        request_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> str:
        completed_at = utc_now()
        llm_call_id = generate_prefixed_id("llm")
        with self.uow_factory() as uow:
            uow.llm_calls.insert(
                LLMCallRecord(
                    llm_call_id=llm_call_id,
                    task_id=context.task_id,
                    task_run_id=context.task_run_id,
                    node_id=context.node_id,
                    node_run_id=context.node_run_id,
                    trace_id=context.node_run_id,
                    phase="node_execution",
                    role=context.role,
                    model_profile=profile.name,
                    provider=profile.provider,
                    endpoint=profile.base_url,
                    supports_tools=bool(tools),
                    request_tokens=response.prompt_tokens,
                    response_tokens=response.completion_tokens,
                    total_tokens=response.total_tokens,
                    latency_ms=max(int((completed_at - started_at).total_seconds() * 1000), 0),
                    status=LLMCallStatus.SUCCESS,
                    request_summary_json={
                        "message_count": len(request_messages),
                        "tool_names": [item["function"]["name"] for item in tools],
                        "last_input_preview": self._message_preview(request_messages[-1]),
                    },
                    response_summary_json={
                        "finish_reason": response.finish_reason,
                        "tool_names": [item.name for item in response.tool_calls],
                        "content_preview": compact_text(response.content, 240),
                    },
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )
        return llm_call_id

    def _record_llm_failure(
        self,
        context: NodeExecutionContext,
        *,
        profile: ModelProfile,
        error: Exception,
        started_at,
        request_messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> None:
        completed_at = utc_now()
        with self.uow_factory() as uow:
            uow.llm_calls.insert(
                LLMCallRecord(
                    llm_call_id=generate_prefixed_id("llm"),
                    task_id=context.task_id,
                    task_run_id=context.task_run_id,
                    node_id=context.node_id,
                    node_run_id=context.node_run_id,
                    trace_id=context.node_run_id,
                    phase="node_execution",
                    role=context.role,
                    model_profile=profile.name,
                    provider=profile.provider,
                    endpoint=profile.base_url,
                    supports_tools=bool(tools),
                    status=LLMCallStatus.ERROR,
                    request_summary_json={
                        "message_count": len(request_messages),
                        "tool_names": [item["function"]["name"] for item in tools],
                        "last_input_preview": self._message_preview(request_messages[-1]),
                    },
                    response_summary_json={},
                    error_json={"type": type(error).__name__, "message": str(error)},
                    started_at=started_at,
                    completed_at=completed_at,
                )
            )

    @staticmethod
    def _fallback_descriptor(tool_name: str) -> ToolDescriptor:
        return ToolDescriptor(
            name=tool_name,
            description="Dynamically requested tool call.",
            category=ToolCategory.BUILTIN,
            risk_level=RiskLevel.READ,
            input_schema={"type": "object", "additionalProperties": True},
        )

    @staticmethod
    def _sandbox_run_record(
        *,
        tool_call_id: str,
        sandbox_result,
        started_at,
        completed_at,
    ) -> SandboxRunRecord:
        return SandboxRunRecord(
            sandbox_run_id=generate_prefixed_id("sbox"),
            tool_call_id=tool_call_id,
            profile_name=sandbox_result.profile_name,
            image_name=sandbox_result.image_name,
            network_enabled=sandbox_result.network_enabled,
            mounts_json=sandbox_result.mounts_json,
            command_text=sandbox_result.command_text,
            exit_code=sandbox_result.exit_code,
            timed_out=sandbox_result.timed_out,
            stdout_excerpt=sandbox_result.stdout_excerpt,
            stderr_excerpt=sandbox_result.stderr_excerpt,
            started_at=started_at,
            completed_at=completed_at,
        )

    @staticmethod
    def _message_preview(message: dict[str, Any]) -> str:
        content = message.get("content")
        if isinstance(content, str):
            return compact_text(content, 240)
        if content is None:
            return ""
        return compact_text(str(content), 240)

    @staticmethod
    def _system_prompt(context: NodeExecutionContext) -> str:
        return (
            "You are an execution agent responsible for one task node. "
            "Use the provided tools only when they materially help. "
            "Do not invent tool results. Keep the final answer concise, concrete, and grounded in the completed work."
        )

    def _user_prompt(self, context: NodeExecutionContext) -> str:
        workspace_root = self.tool_registry.workspace_root.as_posix()
        return (
            f"Role: {context.role}\n"
            f"Task title: {context.task_title}\n"
            f"Node title: {context.title}\n"
            f"Objective: {context.objective}\n"
            f"Node goal: {context.goal}\n"
            f"Success criteria: {json.dumps(context.success_criteria, ensure_ascii=False)}\n"
            f"Constraints: {json.dumps(context.constraints, ensure_ascii=False)}\n"
            f"Expected outputs: {json.dumps(context.expected_outputs, ensure_ascii=False)}\n"
            f"Workspace root: {workspace_root}\n"
            f"Risk level: {context.risk_level.value}\n"
            "When you finish, return a plain-text final answer."
        )
