from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.api.deps import resolve_container_from_request
from src.application.api.presenters import build_task_read, build_task_run_read
from src.application.api.schemas import (
    TaskDetailResponse,
    TaskListResponse,
    TaskRunDetailResponse,
    TaskRunListResponse,
)
from src.shared.schemas import TaskStatus

router = APIRouter(prefix="/api/v1", tags=["tasks"])


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    session_id: str | None = None,
    status: TaskStatus | None = None,
    limit: int = Query(default=20, ge=1, le=200),
    container=Depends(resolve_container_from_request),
) -> TaskListResponse:
    with container.uow_factory() as uow:
        if session_id:
            records = uow.tasks.list_by_session(session_id, limit=limit)
        elif status is not None:
            records = uow.tasks.list_by_status(status, limit=limit)
        else:
            records = uow.tasks.list_recent(limit=limit)
        return TaskListResponse(
            items=[
                build_task_read(
                    uow,
                    item,
                    include_current_run=False,
                    include_latest_run=False,
                    include_nodes=False,
                )
                for item in records
            ]
        )


@router.get("/tasks/{task_id}", response_model=TaskDetailResponse)
def get_task(
    task_id: str,
    container=Depends(resolve_container_from_request),
) -> TaskDetailResponse:
    with container.uow_factory() as uow:
        record = uow.tasks.get(task_id)
        if record is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        return TaskDetailResponse(task=build_task_read(uow, record, include_nodes=True))


@router.get("/tasks/{task_id}/runs", response_model=TaskRunListResponse)
def list_task_runs(
    task_id: str,
    container=Depends(resolve_container_from_request),
) -> TaskRunListResponse:
    with container.uow_factory() as uow:
        task = uow.tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task_not_found")
        runs = uow.task_runs.list_by_task(task_id)
        return TaskRunListResponse(
            items=[build_task_run_read(uow, run, include_nodes=True) for run in runs]
        )


@router.get("/runs/{task_run_id}", response_model=TaskRunDetailResponse)
def get_task_run(
    task_run_id: str,
    container=Depends(resolve_container_from_request),
) -> TaskRunDetailResponse:
    with container.uow_factory() as uow:
        run = uow.task_runs.get(task_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="task_run_not_found")
        return TaskRunDetailResponse(run=build_task_run_read(uow, run, include_nodes=True))
