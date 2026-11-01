import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status

from app.config import AppConfig, load_config
from app.llm.registry import AdapterRegistry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    registry: AdapterRegistry | None = None
    try:
        config: AppConfig = load_config()
        registry = AdapterRegistry(config)
        app.state.config = config
        app.state.registry = registry
        app.state.is_healthy = True
        logger.info("Application initialized successfully")
    except Exception:
        app.state.config = None
        app.state.registry = None
        app.state.is_healthy = False
        logger.exception("Failed to load configuration at startup")

    yield

    if registry is not None:
        await registry.close()
        logger.info("Application resources closed cleanly")


app = FastAPI(title="VaaniKit", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health(response: Response) -> dict[str, str]:
    is_healthy: bool = getattr(app.state, "is_healthy", False)
    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "message": "Service unavailable"}
    return {"status": "ok", "message": "Service healthy"}
