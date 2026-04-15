from __future__ import annotations

import os
from pathlib import Path

from fastapi import HTTPException, Request, WebSocket

from src.services import build_service_container


def default_db_path() -> Path:
    configured = os.getenv("SWARM_DB_PATH")
    if configured:
        return Path(configured)
    return Path.cwd() / "data" / "swarm.sqlite3"


def resolve_container_from_request(request: Request):
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(status_code=500, detail="service_container_not_initialized")
    return container


def resolve_container_from_websocket(websocket: WebSocket):
    container = getattr(websocket.app.state, "container", None)
    if container is None:
        raise RuntimeError("service_container_not_initialized")
    return container


def create_default_container():
    return build_service_container(default_db_path())
