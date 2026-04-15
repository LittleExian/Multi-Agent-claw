from __future__ import annotations

from src.runtime.contracts import NodeExecutionContext, NodeExecutionResult


class NodeExecutionError(RuntimeError):
    def __init__(self, error_code: str, error_message: str, *, retryable: bool = False):
        super().__init__(error_message)
        self.error_code = error_code
        self.error_message = error_message
        self.retryable = retryable


class DefaultNodeExecutor:
    """Small deterministic executor used for the MVP runtime path."""

    def execute(self, context: NodeExecutionContext) -> NodeExecutionResult:
        lowered_goal = context.goal.lower()
        if context.node_metadata_json.get("force_error") or "force_fail" in lowered_goal:
            raise NodeExecutionError(
                "runtime.forced_failure",
                "Node execution was forced to fail for testing.",
                retryable=False,
            )

        role = context.role.lower()
        if role == "coder":
            return self._execute_coder(context)
        if role in {"researcher", "browser"}:
            return self._execute_research(context)
        if role == "writer":
            return self._execute_writer(context)
        return self._execute_coordinator(context)

    def _execute_coder(self, context: NodeExecutionContext) -> NodeExecutionResult:
        checks = ["分析任务目标", "整理修改建议", "生成执行摘要"]
        return NodeExecutionResult(
            output_summary=f"已完成 {context.title}，整理了代码执行建议。",
            output_json={
                "role": "coder",
                "goal": context.goal,
                "checks": checks,
                "proposed_changes": [
                    f"围绕目标 '{context.objective}' 推进实现",
                    "确认受影响模块与潜在风险",
                    "生成后续总结所需的结构化结果",
                ],
            },
            metadata_json={"executor": "default_runtime"},
        )

    def _execute_research(self, context: NodeExecutionContext) -> NodeExecutionResult:
        findings = [
            f"已围绕 '{context.objective}' 建立信息提纲",
            "提炼了关键要点与输出方向",
            "为总结阶段准备了结构化输入",
        ]
        return NodeExecutionResult(
            output_summary=f"已完成 {context.title}，输出了研究要点。",
            output_json={
                "role": context.role,
                "goal": context.goal,
                "findings": findings,
            },
            metadata_json={"executor": "default_runtime"},
        )

    def _execute_writer(self, context: NodeExecutionContext) -> NodeExecutionResult:
        outputs = context.expected_outputs or ["result_summary"]
        return NodeExecutionResult(
            output_summary=f"已生成最终输出：{', '.join(outputs)}。",
            output_json={
                "role": "writer",
                "deliverable_type": outputs,
                "summary": f"围绕 '{context.task_title}' 生成了最终交付内容。",
                "structure": [
                    "背景与目标",
                    "执行结果",
                    "后续建议",
                ],
            },
            metadata_json={"executor": "default_runtime"},
        )

    def _execute_coordinator(self, context: NodeExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(
            output_summary=f"已完成协调节点 {context.title}。",
            output_json={
                "role": "coordinator",
                "goal": context.goal,
                "next_actions": [
                    "确认当前阶段结果",
                    "准备后续节点所需输入",
                ],
            },
            metadata_json={"executor": "default_runtime"},
        )
