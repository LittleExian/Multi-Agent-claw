from __future__ import annotations

from src.shared.schemas import (
    ApprovalStatus,
    MessageAttachmentRecord,
    MessageDirection,
    MessageRole,
    MessageRecord,
    SessionKind,
    SessionRecord,
    SessionStatus,
    TaskEventType,
    TaskStatus,
)

from .base import ServiceBase
from .models import (
    ApprovalDecision,
    InboundAttachment,
    InboundEnvelope,
    IntakeDecision,
    IntakeDecisionKind,
    TaskDraft,
)
from .utils import compact_text, generate_prefixed_id


class TaskIntakeService(ServiceBase):
    START_HINTS = (
        "开始任务",
        "开始执行",
        "帮我完成",
        "按步骤推进",
        "处理一下",
        "start task",
    )
    RESUME_HINTS = ("继续", "继续执行", "resume", "继续这个任务", "接着来")
    APPROVE_HINTS = ("同意", "确认", "批准", "approve", "yes", "可以", "继续执行")
    REJECT_HINTS = ("拒绝", "取消", "reject", "no", "不要", "别执行")

    def handle_inbound(self, envelope: InboundEnvelope) -> IntakeDecision:
        session_id = envelope.session_id or self._derive_session_id(envelope)
        with self.uow_factory() as uow:
            self._ensure_session(uow, envelope, session_id)
            message = self._persist_message(uow, envelope, session_id)
            self._persist_attachments(uow, envelope.attachments, message.message_id, envelope.received_at)
            uow.sessions.touch(session_id, envelope.received_at)

            active_task = uow.tasks.latest_active_for_session(session_id)
            pending_approval = None
            if active_task and active_task.current_run_id:
                pending = uow.approvals.list_pending(task_run_id=active_task.current_run_id)
                pending_approval = pending[0] if pending else None

            self._emit_event(
                uow,
                event_type=TaskEventType.SESSION_MESSAGE_RECEIVED,
                session_id=session_id,
                task_id=active_task.task_id if active_task else None,
                task_run_id=active_task.current_run_id if active_task else None,
                emitted_by="task_intake",
                payload_json={
                    "message_id": message.message_id,
                    "content_preview": compact_text(message.content_text or "", 60),
                    "attachment_count": len(envelope.attachments),
                },
            )

            content = (envelope.content or "").strip()
            approval_decision = self._parse_approval_decision(content)
            if pending_approval and approval_decision is not None:
                return IntakeDecision(
                    kind=IntakeDecisionKind.APPROVAL_REPLY,
                    session_id=session_id,
                    source_message_id=message.message_id,
                    task_id=active_task.task_id if active_task else None,
                    task_run_id=active_task.current_run_id if active_task else None,
                    approval_id=pending_approval.approval_id,
                    approval_decision=approval_decision,
                    reason="matched_pending_approval",
                )

            explicit_start = self._has_any_hint(content, self.START_HINTS) or bool(
                envelope.metadata_json.get("start_task")
            )
            resume_signal = self._has_any_hint(content, self.RESUME_HINTS)
            has_attachments = bool(envelope.attachments)
            has_meaningful_content = bool(content)

            if active_task and active_task.status == TaskStatus.NEEDS_CLARIFICATION and has_meaningful_content:
                return IntakeDecision(
                    kind=IntakeDecisionKind.CLARIFICATION_REPLY,
                    session_id=session_id,
                    source_message_id=message.message_id,
                    task_id=active_task.task_id,
                    task_run_id=active_task.current_run_id,
                    draft=self._build_draft(envelope, session_id, message.message_id, explicit_start=False, referenced_task_id=active_task.task_id),
                    reason="active_task_needs_clarification",
                )

            if active_task and resume_signal and not explicit_start:
                return IntakeDecision(
                    kind=IntakeDecisionKind.RESUME_TASK,
                    session_id=session_id,
                    source_message_id=message.message_id,
                    task_id=active_task.task_id,
                    task_run_id=active_task.current_run_id,
                    reason="matched_resume_signal",
                )

            should_start = explicit_start or has_attachments or self._looks_like_task_request(content)
            if should_start:
                return IntakeDecision(
                    kind=IntakeDecisionKind.NEW_TASK,
                    session_id=session_id,
                    source_message_id=message.message_id,
                    draft=self._build_draft(
                        envelope,
                        session_id,
                        message.message_id,
                        explicit_start=explicit_start,
                    ),
                    reason="explicit_or_high_confidence_task",
                )

            return IntakeDecision(
                kind=IntakeDecisionKind.CHAT,
                session_id=session_id,
                source_message_id=message.message_id,
                reason="default_chat_fallback",
            )

    def _ensure_session(self, uow, envelope: InboundEnvelope, session_id: str) -> SessionRecord:
        existing = uow.sessions.get(session_id)
        if existing is not None:
            return existing
        session = SessionRecord(
            session_id=session_id,
            channel=envelope.channel,
            user_id=envelope.user_id,
            session_kind=self._infer_session_kind(envelope.channel, session_id),
            title=None,
            status=SessionStatus.ACTIVE,
            source_ref=envelope.metadata_json.get("source_ref"),
            metadata_json=envelope.metadata_json,
            created_at=envelope.received_at,
            updated_at=envelope.received_at,
        )
        uow.sessions.insert(session)
        return session

    def _persist_message(self, uow, envelope: InboundEnvelope, session_id: str) -> MessageRecord:
        message = MessageRecord(
            message_id=envelope.message_id,
            session_id=session_id,
            channel=envelope.channel,
            direction=MessageDirection.INBOUND,
            role=MessageRole.USER,
            channel_message_id=envelope.metadata_json.get("channel_message_id"),
            reply_to_message_id=envelope.metadata_json.get("reply_to_message_id"),
            content_text=envelope.content or "",
            metadata_json=envelope.metadata_json,
            received_at=envelope.received_at,
            created_at=envelope.received_at,
        )
        uow.messages.insert(message)
        return message

    def _persist_attachments(
        self,
        uow,
        attachments: list[InboundAttachment],
        message_id: str,
        created_at,
    ) -> None:
        for attachment in attachments:
            record = MessageAttachmentRecord(
                attachment_id=generate_prefixed_id("att"),
                message_id=message_id,
                name=attachment.name,
                mime_type=attachment.mime_type,
                size_bytes=attachment.size_bytes,
                sha256=attachment.sha256,
                storage_uri=attachment.storage_uri,
                extracted_text_uri=attachment.extracted_text_uri,
                metadata_json=attachment.metadata_json,
                created_at=created_at,
            )
            uow.message_attachments.insert(record)

    def _build_draft(
        self,
        envelope: InboundEnvelope,
        session_id: str,
        source_message_id: str,
        *,
        explicit_start: bool,
        referenced_task_id: str | None = None,
    ) -> TaskDraft:
        return TaskDraft(
            session_id=session_id,
            source_message_id=source_message_id,
            user_id=envelope.user_id,
            channel=envelope.channel,
            content=envelope.content or "",
            attachments=envelope.attachments,
            explicit_start=explicit_start,
            referenced_task_id=referenced_task_id,
            metadata_json=envelope.metadata_json,
        )

    def _derive_session_id(self, envelope: InboundEnvelope) -> str:
        if envelope.channel == "web":
            browser_session = envelope.metadata_json.get("browser_session_id", "default")
            return f"web:{envelope.user_id}:{browser_session}"
        if envelope.channel == "cli":
            return f"cli:{envelope.user_id}"
        peer = envelope.metadata_json.get("peer_id") or envelope.user_id
        return f"{envelope.channel}:dm:{peer}"

    def _infer_session_kind(self, channel: str, session_id: str) -> SessionKind:
        if channel == "web":
            return SessionKind.WEB
        if channel == "cli":
            return SessionKind.CLI
        if ":group:" in session_id and ":thread:" in session_id:
            return SessionKind.THREAD
        if ":group:" in session_id:
            return SessionKind.GROUP
        return SessionKind.DM

    def _looks_like_task_request(self, content: str) -> bool:
        lowered = content.lower()
        keywords = (
            "帮我",
            "请你",
            "调研",
            "整理",
            "写一份",
            "分析",
            "修复",
            "运行",
            "生成",
            "创建",
            "compare",
            "research",
            "fix",
            "generate",
        )
        return any(keyword in lowered for keyword in keywords)

    def _parse_approval_decision(self, content: str) -> ApprovalDecision | None:
        if self._has_any_hint(content, self.APPROVE_HINTS):
            return ApprovalDecision.APPROVE
        if self._has_any_hint(content, self.REJECT_HINTS):
            return ApprovalDecision.REJECT
        return None

    @staticmethod
    def _has_any_hint(content: str, hints: tuple[str, ...]) -> bool:
        lowered = content.lower()
        return any(hint.lower() in lowered for hint in hints)
