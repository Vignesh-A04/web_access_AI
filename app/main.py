"""FastAPI application entrypoint with lifespan events, CORS, and routing."""

import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router, test_site_router
from app.config import settings
from app.logging.setup import get_logger, setup_logging
from app.services.task_service import task_service

# Initialize logging early
setup_logging(level=settings.log_level, structured=True)
logger = get_logger("app.main")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing startup validation and clean shutdown."""
    logger.info("Initializing AI Web Automation Agent application...")
    logger.info(
        f"Server configured on {settings.backend_host}:{settings.backend_port} "
        f"| Gemini model: {settings.gemini_model} "
        f"| Browser headless: {settings.browser_headless} "
        f"| Local test mode: {settings.allow_local_test_domains}"
    )

    yield

    logger.info("Shutting down AI Web Automation Agent and cleaning resources...")
    await task_service.shutdown()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="AI Web Automation Agent",
    description="Generic Autonomous AI Web Automation Agent powered by Google Gemini and Playwright.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration
allowed_origins = [
    settings.frontend_origin,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(api_router)
app.include_router(test_site_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.backend_host,
        port=settings.backend_port,
        reload=False,
    )
