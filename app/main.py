import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.admin.routes import STATIC_DIR
from app.admin.routes import router as admin_router
from app.api.voice import router as voice_router
from app.config import AppConfig, Settings, load_config
from app.db.seed import seed_demo_data
from app.db.session import Database
from app.llm.registry import AdapterRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    registry: AdapterRegistry | None = None
    database: Database | None = None

    try:
        config: AppConfig = load_config(settings.agent_config_path or None)
        database = Database(config.database.url)
        database.create_schema()

        if settings.seed_demo_data:
            with database.session() as session:
                seed_demo_data(session)

        registry = AdapterRegistry(config)

        app.state.config = config
        app.state.database = database
        app.state.session_factory = database.session_factory
        app.state.registry = registry
        app.state.is_healthy = True
        logger.info("Application initialised")
    except Exception:
        logger.exception("Application startup failed")
        app.state.config = None
        app.state.database = None
        app.state.session_factory = None
        app.state.registry = None
        app.state.is_healthy = False

    yield

    if registry is not None:
        await registry.close()
    if database is not None:
        database.dispose()
    logger.info("Application resources closed cleanly")


app = FastAPI(title="VaaniKit", version="0.1.0", lifespan=lifespan)
app.include_router(admin_router)
app.include_router(voice_router)
app.mount("/admin/static", StaticFiles(directory=STATIC_DIR), name="admin-static")


@app.middleware("http")
async def security_headers_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response



@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    return RedirectResponse(url="/admin/ui")


@app.get("/demo", include_in_schema=False)
def voice_demo() -> FileResponse:
    return FileResponse(STATIC_DIR / "voice.html", media_type="text/html")


@app.get("/health")
async def health(response: Response) -> dict[str, str]:
    is_healthy: bool = getattr(app.state, "is_healthy", False)
    database = getattr(app.state, "database", None)
    database_ok = database.check() if isinstance(database, Database) else False

    if not is_healthy or not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": "Service unavailable", "database": "unavailable"}

    return {"status": "ok", "message": "Service healthy", "database": "ok"}
