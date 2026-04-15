from __future__ import annotations

from fastapi import APIRouter, Depends, status

from src.application.api.deps import resolve_container_from_request
from src.application.api.presenters import (
    build_task_lifecycle_result,
    build_task_read,
    build_task_run_read,
    to_approval_read,
    to_session_read,
)
from src.application.api.schemas import GatewayMessageRequest, GatewayMessageResponse
from src.services import InboundAttachment, InboundEnvelope
from src.services.utils import generate_prefixed_id, utc_now

router = APIRouter(prefix="/api/v1/gateway", tags=["gateway"])


@router.post(
    "/messages",
    response_model=GatewayMessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def ingest_message(
    payload: GatewayMessageRequest,
    container=Depends(resolve_container_from_request),
) -> GatewayMessageResponse:
    received_at = payload.received_at or utc_now()
    message_id = payload.message_id or generate_prefixed_id("msg")
    result = container.task_workflow.process_inbound(
        InboundEnvelope(
            message_id=message_id,
            session_id=payload.session_id,
            user_id=payload.user_id,
            channel=payload.channel,
            content=payload.content,
            attachments=[
                InboundAttachment(
                    name=item.name,
                    storage_uri=item.storage_uri,
                    mime_type=item.mime_type,
                    size_bytes=item.size_bytes,
                    sha256=item.sha256,
                    extracted_text_uri=item.extracted_text_uri,
                    metadata_json=item.metadata_json,
                )
                for item in payload.attachments
            ],
            metadata_json=payload.metadata_json,
            received_at=received_at,
        )
    )
    if result.task_run_id and result.status == "running":
        container.worker_loop.drain_run(result.task_run_id)

    with container.uow_factory() as uow:
        session = uow.sessions.get(result.session_id)
        if session is None:
            raise RuntimeError(f"Session not found after intake: {result.session_id}")
        result = build_task_lifecycle_result(
            uow,
            session_id=result.session_id,
            task_id=result.task_id,
            task_run_id=result.task_run_id,
            intake_kind=result.intake_kind,
        )
        task = uow.tasks.get(result.task_id) if result.task_id else None
        run = uow.task_runs.get(result.task_run_id) if result.task_run_id else None
        approval = uow.approvals.get(result.approval_id) if result.approval_id else None
        return GatewayMessageResponse(
            message_id=message_id,
            session=to_session_read(session),
            result=result,
            task=build_task_read(uow, task, include_nodes=True) if task is not None else None,
            run=build_task_run_read(uow, run, include_nodes=True) if run is not None else None,
            approval=to_approval_read(approval) if approval is not None else None,
        )
