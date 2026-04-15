from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.application.api.deps import resolve_container_from_request
from src.application.api.presenters import build_task_lifecycle_result, to_approval_read
from src.application.api.schemas import (
    ApprovalDetailResponse,
    ApprovalListResponse,
    ApprovalResolveRequest,
    ApprovalResolveResponse,
)
from src.services import ApprovalResolutionPayload

router = APIRouter(prefix="/api/v1", tags=["approvals"])


@router.get("/approvals/{approval_id}", response_model=ApprovalDetailResponse)
def get_approval(
    approval_id: str,
    container=Depends(resolve_container_from_request),
) -> ApprovalDetailResponse:
    with container.uow_factory() as uow:
        approval = uow.approvals.get(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval_not_found")
        return ApprovalDetailResponse(approval=to_approval_read(approval))


@router.get("/runs/{task_run_id}/approvals", response_model=ApprovalListResponse)
def list_run_approvals(
    task_run_id: str,
    container=Depends(resolve_container_from_request),
) -> ApprovalListResponse:
    with container.uow_factory() as uow:
        run = uow.task_runs.get(task_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="task_run_not_found")
        items = [to_approval_read(record) for record in uow.approvals.list_by_run(task_run_id)]
        return ApprovalListResponse(items=items)


@router.post("/approvals/{approval_id}/resolve", response_model=ApprovalResolveResponse)
def resolve_approval(
    approval_id: str,
    payload: ApprovalResolveRequest,
    container=Depends(resolve_container_from_request),
) -> ApprovalResolveResponse:
    session_id = ""
    with container.uow_factory() as uow:
        existing = uow.approvals.get(approval_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="approval_not_found")
        task = uow.tasks.get(existing.task_id)
        if task is not None:
            session_id = task.session_id

    approval = container.orchestrator.resolve_approval(
        ApprovalResolutionPayload(
            approval_id=approval_id,
            decision=payload.decision,
            decided_by=payload.decided_by,
            edited_actions=payload.edited_actions,
        )
    )
    if approval.status.value in {"approved", "edited"}:
        container.worker_loop.drain_run(approval.task_run_id)

    with container.uow_factory() as uow:
        result = build_task_lifecycle_result(
            uow,
            session_id=session_id,
            task_id=approval.task_id,
            task_run_id=approval.task_run_id,
        )

    return ApprovalResolveResponse(
        approval=to_approval_read(approval),
        result=result,
    )
