"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ichnos import __version__
from ichnos.api.config import router as config_router
from ichnos.api.health import router as health_router
from ichnos.api.intake import router as intake_router
from ichnos.api.knowledge import router as knowledge_router
from ichnos.api.sync import router as sync_router
from ichnos.api.workspaces import router as workspaces_router
from ichnos.db.engine import make_engine, make_session_factory
from ichnos.db.migrate import upgrade_to_head
from ichnos.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    engine = make_engine(config)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        upgrade_to_head(config.sqlalchemy_url())
        yield
        engine.dispose()

    app = FastAPI(
        title="Ichnos API",
        version=__version__,
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = config
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.github_transport = None  # tests inject httpx.MockTransport here
    app.state.llm_transport = None  # tests inject httpx.MockTransport here
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(config_router)
    app.include_router(workspaces_router)
    app.include_router(sync_router)
    app.include_router(knowledge_router)
    app.include_router(intake_router)
    return app


app = create_app()
