from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.application.api.deps import create_default_container
from src.application.api.routes import (
    approvals_router,
    events_router,
    gateway_router,
    tasks_router,
)
from src.application.api.schemas import HealthResponse
from src.services import build_service_container
from src.shared.schemas.common import SCHEMA_VERSION


def create_app(*, db_path: str | Path | None = None, container=None) -> FastAPI:
    service_container = container or (
        build_service_container(db_path) if db_path is not None else create_default_container()
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = service_container
        service_container.event_bus.attach_loop()
        try:
            yield
        finally:
            service_container.event_bus.close()
            service_container.db.close()

    app = FastAPI(
        title="Multi-Agent Claw API",
        version=SCHEMA_VERSION,
        lifespan=lifespan,
    )
    app.include_router(gateway_router)
    app.include_router(tasks_router)
    app.include_router(approvals_router)
    app.include_router(events_router)

    @app.get("/healthz", response_model=HealthResponse, tags=["system"])
    def healthz() -> HealthResponse:
        return HealthResponse(
            status="ok",
            db_path=str(service_container.db.db_path),
            schema_version=SCHEMA_VERSION,
        )

    return app
