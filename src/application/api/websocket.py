from __future__ import annotations

import asyncio
from contextlib import suppress
from time import monotonic

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from src.application.api.presenters import build_run_snapshot, to_task_event_envelope
from src.application.api.schemas import RunEventStreamQuery
from src.shared.schemas import (
    TaskEventRecord,
    WebSocketAckMessage,
    WebSocketErrorMessage,
    WebSocketErrorPayload,
    WebSocketEventMessage,
    WebSocketHeartbeatMessage,
    WebSocketHeartbeatPayload,
    WebSocketSnapshotMessage,
)
from src.services.utils import utc_now


async def _send_model(websocket: WebSocket, model) -> None:
    await websocket.send_text(model.model_dump_json())


def _resolve_session_id(container, task_run_id: str) -> str:
    with container.uow_factory() as uow:
        run = uow.task_runs.get(task_run_id)
        if run is None:
            raise ValueError(f"Task run not found: {task_run_id}")
        task = uow.tasks.get(run.task_id)
        if task is None:
            raise ValueError(f"Task not found for run: {task_run_id}")
        return task.session_id


def _load_run_events(container, task_run_id: str, after_seq: int) -> list:
    with container.uow_factory() as uow:
        return uow.task_events.list_by_run(task_run_id, after_seq=after_seq)


def _load_run_snapshot(container, task_run_id: str):
    with container.uow_factory() as uow:
        return build_run_snapshot(uow, task_run_id)


async def stream_run_events(
    websocket: WebSocket,
    container,
    *,
    task_run_id: str,
    query: RunEventStreamQuery,
) -> None:
    await websocket.accept()
    receive_task: asyncio.Task[str] | None = None
    event_task: asyncio.Task[TaskEventRecord] | None = None
    try:
        session_id = await asyncio.to_thread(_resolve_session_id, container, task_run_id)
    except ValueError as exc:
        await _send_model(
            websocket,
            WebSocketErrorMessage(
                session_id=None,
                task_run_id=task_run_id,
                data=WebSocketErrorPayload(
                    code="task_run_not_found",
                    message=str(exc),
                ),
            ),
        )
        await websocket.close(code=4404)
        return

    subscription = await container.event_bus.subscribe_run(task_run_id)
    cursor = query.cursor
    await _send_model(
        websocket,
        WebSocketAckMessage(
            cursor=cursor,
            session_id=session_id,
            task_run_id=task_run_id,
            data={"status": "subscribed"},
        ),
    )

    if query.include_snapshot:
        snapshot = await asyncio.to_thread(_load_run_snapshot, container, task_run_id)
        await _send_model(
            websocket,
            WebSocketSnapshotMessage(
                cursor=cursor,
                session_id=snapshot.session_id,
                task_run_id=task_run_id,
                data=snapshot.data,
            ),
        )

    try:
        backlog = await asyncio.to_thread(_load_run_events, container, task_run_id, cursor)
        for record in backlog:
            event = to_task_event_envelope(record)
            cursor = max(cursor, event.sequence)
            await _send_model(
                websocket,
                WebSocketEventMessage(
                    cursor=cursor,
                    session_id=event.session_id,
                    task_run_id=task_run_id,
                    data=event,
                ),
            )

        last_heartbeat_at = monotonic()
        heartbeat_interval = max(query.heartbeat_interval_ms / 1000, 1.0)
        receive_task = asyncio.create_task(websocket.receive_text())
        event_task = asyncio.create_task(subscription.queue.get())

        while True:
            timeout = max(heartbeat_interval - (monotonic() - last_heartbeat_at), 0.0)
            done, _ = await asyncio.wait(
                {receive_task, event_task},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                await _send_model(
                    websocket,
                    WebSocketHeartbeatMessage(
                        cursor=cursor,
                        session_id=session_id,
                        task_run_id=task_run_id,
                        data=WebSocketHeartbeatPayload(server_time=utc_now()),
                    ),
                )
                last_heartbeat_at = monotonic()
                continue

            if event_task in done:
                record = event_task.result()
                event_task = asyncio.create_task(subscription.queue.get())
                cursor = await _forward_event(
                    websocket,
                    record,
                    task_run_id=task_run_id,
                    cursor=cursor,
                )

            if receive_task in done:
                try:
                    message = receive_task.result()
                except WebSocketDisconnect:
                    break
                receive_task = asyncio.create_task(websocket.receive_text())
                normalized = message.strip().lower()
                if normalized == "snapshot":
                    snapshot = await asyncio.to_thread(_load_run_snapshot, container, task_run_id)
                    await _send_model(
                        websocket,
                        WebSocketSnapshotMessage(
                            cursor=cursor,
                            session_id=snapshot.session_id,
                            task_run_id=task_run_id,
                            data=snapshot.data,
                        ),
                    )
    finally:
        container.event_bus.unsubscribe(subscription)
        if receive_task is not None:
            with suppress(BaseException):
                receive_task.cancel()
            with suppress(BaseException):
                await receive_task
        if event_task is not None:
            with suppress(BaseException):
                event_task.cancel()
            with suppress(BaseException):
                await event_task


async def _forward_event(
    websocket: WebSocket,
    record: TaskEventRecord,
    *,
    task_run_id: str,
    cursor: int,
) -> int:
    event = to_task_event_envelope(record)
    if event.sequence <= cursor:
        return cursor
    await _send_model(
        websocket,
        WebSocketEventMessage(
            cursor=event.sequence,
            session_id=event.session_id,
            task_run_id=task_run_id,
            data=event,
        ),
    )
    return event.sequence
