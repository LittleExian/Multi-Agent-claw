from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket

from src.application.api.deps import resolve_container_from_request, resolve_container_from_websocket
from src.application.api.presenters import build_run_snapshot, to_task_event_envelope
from src.application.api.schemas import EventListResponse, RunEventStreamQuery, RunSnapshotResponse
from src.application.api.websocket import stream_run_events

router = APIRouter(prefix="/api/v1", tags=["events"])


@router.get("/sessions/{session_id}/events", response_model=EventListResponse)
def list_session_events(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    container=Depends(resolve_container_from_request),
) -> EventListResponse:
    with container.uow_factory() as uow:
        session = uow.sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        items = [to_task_event_envelope(item) for item in uow.task_events.list_by_session(session_id, limit=limit)]
        return EventListResponse(
            session_id=session_id,
            items=items,
        )


@router.get("/runs/{task_run_id}/events", response_model=EventListResponse)
def list_run_events(
    task_run_id: str,
    after_seq: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    container=Depends(resolve_container_from_request),
) -> EventListResponse:
    with container.uow_factory() as uow:
        run = uow.task_runs.get(task_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="task_run_not_found")
        task = uow.tasks.get(run.task_id)
        items = [
            to_task_event_envelope(item)
            for item in uow.task_events.list_by_run(task_run_id, after_seq=after_seq, limit=limit)
        ]
        return EventListResponse(
            session_id=items[0].session_id if items else (task.session_id if task is not None else None),
            task_run_id=task_run_id,
            after_seq=after_seq,
            next_cursor=items[-1].sequence if items else after_seq,
            items=items,
        )


@router.get("/runs/{task_run_id}/snapshot", response_model=RunSnapshotResponse)
def get_run_snapshot(
    task_run_id: str,
    container=Depends(resolve_container_from_request),
) -> RunSnapshotResponse:
    with container.uow_factory() as uow:
        try:
            return build_run_snapshot(uow, task_run_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.websocket("/ws/runs/{task_run_id}")
async def run_events_websocket(
    websocket: WebSocket,
    task_run_id: str,
    cursor: int = 0,
    include_snapshot: bool = True,
    poll_interval_ms: int = 1000,
    heartbeat_interval_ms: int = 15000,
) -> None:
    container = resolve_container_from_websocket(websocket)
    stream_query = RunEventStreamQuery(
        cursor=cursor,
        include_snapshot=include_snapshot,
        poll_interval_ms=poll_interval_ms,
        heartbeat_interval_ms=heartbeat_interval_ms,
    )
    await stream_run_events(
        websocket,
        container,
        task_run_id=task_run_id,
        query=stream_query,
    )
