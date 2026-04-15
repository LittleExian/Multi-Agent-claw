from __future__ import annotations

from src.shared.schemas import (
    Complexity,
    Priority,
    RiskLevel,
    TaskEventType,
    TaskRecord,
    TaskStatus,
)

from .base import ServiceBase
from .models import IntakeDecision, IntakeDecisionKind, RiskProfile, TaskSpec
from .utils import compact_text, generate_prefixed_id, utc_now


class TaskAnalyzerService(ServiceBase):
    MUTABLE_HINTS = ("写", "修改", "更新", "创建", "生成文件", "rename", "write", "edit", "fix", "save")
    DESTRUCTIVE_HINTS = ("删除", "清理", "移除", "drop", "delete", "remove")
    NETWORK_HINTS = ("联网", "搜索", "浏览", "网页", "官网", "web", "search", "browse", "http")
    COMMAND_HINTS = ("命令", "终端", "shell", "bash", "运行", "command", "terminal")
    ACCOUNT_HINTS = ("邮箱", "calendar", "github", "discord", "telegram", "email")

    def analyze(self, decision: IntakeDecision) -> TaskSpec:
        if decision.kind not in {
            IntakeDecisionKind.NEW_TASK,
            IntakeDecisionKind.RESUME_TASK,
            IntakeDecisionKind.CLARIFICATION_REPLY,
        }:
            raise ValueError(f"Unsupported intake decision for analysis: {decision.kind}")

        now = utc_now()
        with self.uow_factory() as uow:
            existing_task = uow.tasks.get(decision.task_id) if decision.task_id else None
            if decision.kind == IntakeDecisionKind.RESUME_TASK:
                if existing_task is None:
                    raise ValueError("resume_task decision requires an existing task")
                spec = self._task_to_spec(existing_task, decision.source_message_id)
                uow.tasks.update_fields(
                    existing_task.task_id,
                    {"updated_at": now, "status": TaskStatus.QUEUED},
                )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_UPDATED,
                    session_id=existing_task.session_id,
                    task_id=existing_task.task_id,
                    emitted_by="task_analyzer",
                    payload_json={"reason": "resume_requested"},
                )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_STATUS_CHANGED,
                    session_id=existing_task.session_id,
                    task_id=existing_task.task_id,
                    emitted_by="task_analyzer",
                    payload_json={"status": TaskStatus.QUEUED.value},
                )
                return spec

            if decision.draft is None:
                raise ValueError("analysis for new or clarification flow requires a task draft")

            spec = self._build_spec(
                decision=decision,
                existing_task=existing_task,
            )
            clarification_resolved = (
                existing_task is not None
                and existing_task.status == TaskStatus.NEEDS_CLARIFICATION
                and not spec.requires_clarification
            )

            status = (
                TaskStatus.NEEDS_CLARIFICATION
                if spec.requires_clarification
                else TaskStatus.QUEUED
            )

            if existing_task is None:
                task_record = TaskRecord(
                    task_id=spec.task_id,
                    session_id=spec.session_id,
                    source_message_id=spec.source_message_id,
                    title=spec.title,
                    objective=spec.objective,
                    task_kind="general",
                    status=status,
                    priority=Priority.NORMAL,
                    complexity=spec.complexity,
                    risk_level=spec.risk_profile.risk_level,
                    success_criteria_json=spec.success_criteria,
                    constraints_json=spec.constraints,
                    expected_outputs_json=spec.expected_outputs,
                    metadata_json=spec.metadata_json,
                    created_by=decision.draft.user_id,
                    created_at=now,
                    updated_at=now,
                )
                uow.tasks.insert(task_record)
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_CREATED,
                    session_id=spec.session_id,
                    task_id=spec.task_id,
                    emitted_by="task_analyzer",
                    payload_json={
                        "title": spec.title,
                        "objective": spec.objective,
                        "complexity": spec.complexity.value,
                        "risk_level": spec.risk_profile.risk_level.value,
                        "source_message_id": spec.source_message_id,
                    },
                )
            else:
                uow.tasks.update_fields(
                    existing_task.task_id,
                    {
                        "title": spec.title,
                        "objective": spec.objective,
                        "status": status,
                        "complexity": spec.complexity,
                        "risk_level": spec.risk_profile.risk_level,
                        "success_criteria_json": spec.success_criteria,
                        "constraints_json": spec.constraints,
                        "expected_outputs_json": spec.expected_outputs,
                        "metadata_json": spec.metadata_json,
                        "updated_at": now,
                    },
                )
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_UPDATED,
                    session_id=spec.session_id,
                    task_id=spec.task_id,
                    emitted_by="task_analyzer",
                    payload_json={"reason": "task_reanalyzed"},
                )

            self._emit_event(
                uow,
                event_type=TaskEventType.TASK_STATUS_CHANGED,
                session_id=spec.session_id,
                task_id=spec.task_id,
                emitted_by="task_analyzer",
                payload_json={"status": status.value},
            )

            if clarification_resolved:
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_CLARIFICATION_RESOLVED,
                    session_id=spec.session_id,
                    task_id=spec.task_id,
                    emitted_by="task_analyzer",
                    payload_json={"source_message_id": decision.source_message_id},
                )

            if spec.requires_clarification:
                self._emit_event(
                    uow,
                    event_type=TaskEventType.TASK_CLARIFICATION_REQUESTED,
                    session_id=spec.session_id,
                    task_id=spec.task_id,
                    emitted_by="task_analyzer",
                    payload_json={
                        "questions": spec.clarification_questions,
                        "blocking_fields": ["objective", "expected_outputs"],
                    },
                )

            return spec

    def _build_spec(
        self,
        *,
        decision: IntakeDecision,
        existing_task: TaskRecord | None,
    ) -> TaskSpec:
        assert decision.draft is not None
        content = (decision.draft.content or "").strip()
        task_id = existing_task.task_id if existing_task else generate_prefixed_id("tsk")
        title = self._build_title(content, decision.draft.attachments)
        objective = content or "分析上传内容并给出结果"
        risk_profile = self._build_risk_profile(content)
        complexity = self._score_complexity(content, len(decision.draft.attachments))
        recommended_roles = self._recommended_roles(content)
        clarification_questions = self._clarification_questions(content, decision.draft.attachments)

        return TaskSpec(
            task_id=task_id,
            session_id=decision.draft.session_id,
            source_message_id=decision.source_message_id,
            title=title,
            objective=objective,
            success_criteria=self._success_criteria(objective, decision.draft.attachments),
            constraints=self._constraints(content, risk_profile),
            expected_outputs=self._expected_outputs(content),
            recommended_roles=recommended_roles,
            complexity=complexity,
            risk_profile=risk_profile,
            requires_clarification=bool(clarification_questions),
            clarification_questions=clarification_questions,
            metadata_json={
                "attachment_count": len(decision.draft.attachments),
                "explicit_start": decision.draft.explicit_start,
                "recommended_roles": recommended_roles,
                "requires_network": risk_profile.requires_network,
                "requires_file_write": risk_profile.requires_file_write,
                "requires_command_exec": risk_profile.requires_command_exec,
                "requires_external_account": risk_profile.requires_external_account,
                "destructive_actions": risk_profile.destructive_actions,
                "risk_confidence": risk_profile.confidence,
            },
        )

    def _task_to_spec(self, task: TaskRecord, source_message_id: str) -> TaskSpec:
        risk_level = RiskLevel(task.risk_level)
        risk_profile = RiskProfile(
            requires_network=bool(task.metadata_json.get("requires_network")),
            requires_file_write=risk_level in {RiskLevel.MUTABLE, RiskLevel.DESTRUCTIVE},
            requires_command_exec=bool(task.metadata_json.get("requires_command_exec")),
            requires_external_account=bool(task.metadata_json.get("requires_external_account")),
            destructive_actions=task.metadata_json.get("destructive_actions", []),
            confidence=task.metadata_json.get("risk_confidence", 0.5),
            risk_level=risk_level,
        )
        return TaskSpec(
            task_id=task.task_id,
            session_id=task.session_id,
            source_message_id=source_message_id,
            title=task.title,
            objective=task.objective,
            success_criteria=task.success_criteria_json,
            constraints=task.constraints_json,
            expected_outputs=task.expected_outputs_json,
            recommended_roles=task.metadata_json.get("recommended_roles", ["coordinator"]),
            complexity=task.complexity,
            risk_profile=risk_profile,
            metadata_json=task.metadata_json,
        )

    def _build_title(self, content: str, attachments) -> str:
        if content:
            return compact_text(content.splitlines()[0], 48)
        if attachments:
            return f"分析 {len(attachments)} 个附件"
        return "未命名任务"

    def _build_risk_profile(self, content: str) -> RiskProfile:
        lowered = content.lower()
        destructive = [hint for hint in self.DESTRUCTIVE_HINTS if hint.lower() in lowered]
        mutable = [hint for hint in self.MUTABLE_HINTS if hint.lower() in lowered]
        requires_network = any(hint.lower() in lowered for hint in self.NETWORK_HINTS)
        requires_command_exec = any(hint.lower() in lowered for hint in self.COMMAND_HINTS)
        requires_external_account = any(hint.lower() in lowered for hint in self.ACCOUNT_HINTS)
        if destructive:
            risk_level = RiskLevel.DESTRUCTIVE
        elif mutable or requires_command_exec:
            risk_level = RiskLevel.MUTABLE
        else:
            risk_level = RiskLevel.READ
        return RiskProfile(
            requires_network=requires_network,
            requires_file_write=bool(mutable or destructive),
            requires_command_exec=requires_command_exec,
            requires_external_account=requires_external_account,
            destructive_actions=destructive,
            confidence=0.8 if (mutable or destructive or requires_network) else 0.4,
            risk_level=risk_level,
        )

    def _score_complexity(self, content: str, attachment_count: int) -> Complexity:
        lowered = content.lower()
        chain_markers = (
            content.count("然后")
            + content.count("并且")
            + content.count("同时")
            + lowered.count(" and ")
            + lowered.count(" then ")
        )
        score = chain_markers + attachment_count
        if score >= 3:
            return Complexity.COMPLEX
        if score >= 1:
            return Complexity.MODERATE
        return Complexity.SIMPLE

    def _recommended_roles(self, content: str) -> list[str]:
        lowered = content.lower()
        roles: list[str] = []
        if any(key in lowered for key in ("代码", "仓库", "repo", "bug", "fix", "运行")):
            roles.append("coder")
        if any(key in lowered for key in ("调研", "竞品", "research", "search", "资料")):
            roles.append("researcher")
            roles.append("browser")
        if any(key in lowered for key in ("报告", "总结", "write", "report", "文档")):
            roles.append("writer")
        if not roles:
            roles.append("coordinator")
        if "coordinator" not in roles:
            roles.append("coordinator")
        deduped: list[str] = []
        for role in roles:
            if role not in deduped:
                deduped.append(role)
        return deduped

    def _success_criteria(self, objective: str, attachments) -> list[str]:
        criteria = ["任务步骤完成且有明确结果输出"]
        if attachments:
            criteria.append("输入附件已被处理并在输出中体现")
        if "报告" in objective or "report" in objective.lower():
            criteria.append("生成可读的报告或总结")
        return criteria

    def _constraints(self, content: str, risk_profile: RiskProfile) -> list[str]:
        constraints: list[str] = []
        if risk_profile.requires_network:
            constraints.append("需要联网权限")
        if risk_profile.requires_command_exec:
            constraints.append("需要命令执行权限")
        if risk_profile.risk_level == RiskLevel.DESTRUCTIVE:
            constraints.append("必须经过强确认后才能执行破坏性操作")
        if not content.strip():
            constraints.append("用户未提供足够的文本说明")
        return constraints

    def _expected_outputs(self, content: str) -> list[str]:
        lowered = content.lower()
        outputs: list[str] = []
        if "报告" in content or "report" in lowered:
            outputs.append("report")
        if "总结" in content or "summary" in lowered:
            outputs.append("summary")
        if "代码" in content or "fix" in lowered:
            outputs.append("code_changes")
        if not outputs:
            outputs.append("result_summary")
        return outputs

    def _clarification_questions(self, content: str, attachments) -> list[str]:
        questions: list[str] = []
        if not content.strip() and not attachments:
            questions.append("希望我具体完成什么任务？")
        elif len(content.strip()) < 6 and not attachments:
            questions.append("目标有点模糊，希望输出什么结果？")
        if "弄一下" in content and "报告" not in content and "总结" not in content:
            questions.append("完成后希望得到什么形式的输出，例如总结、报告还是代码修改？")
        return questions
