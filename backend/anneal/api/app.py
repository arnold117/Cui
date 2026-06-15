"""FastAPI application factory."""

from fastapi import FastAPI

from anneal.api.deps import lifespan
from anneal.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="Anneal", lifespan=lifespan)
    app.include_router(router, prefix="/api/v1")
    return app
