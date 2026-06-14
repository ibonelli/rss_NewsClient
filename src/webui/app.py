"""FastAPI application factory for pelis-feed web UI."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.webui.routes import router

__all__ = ["create_app"]

_STATIC_DIR = Path(__file__).parent / "static"


def create_app(config: dict, session_factory) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application config dict.
        session_factory: SQLAlchemy sessionmaker instance.

    Returns:
        Configured FastAPI application.
    """
    app = FastAPI(title="pelis-feed", version="1.0.0")

    # Store config and session factory for dependency injection
    app.state.config = config
    app.state.session_factory = session_factory

    # CORS for localhost development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount static files
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    # Include API routes
    app.include_router(router)

    return app
