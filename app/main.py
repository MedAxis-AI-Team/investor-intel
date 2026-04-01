from __future__ import annotations

import contextlib
import logging
import uuid

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routers.analyze_signal import router as analyze_signal_router
from app.api.routers.benchmark import router as benchmark_router
from app.api.routers.generate_digest import router as generate_digest_router
from app.api.routers.health import router as health_router
from app.api.routers.ingest_investor import router as ingest_investor_router
from app.api.routers.score_grants import router as score_grants_router
from app.api.routers.score_investors import router as score_investors_router
from app.config import get_settings
from app.infra.logging import redact_headers
from app.models.common import ApiError, ApiResponse

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        if not settings.anthropic_api_key.strip():
            raise RuntimeError("ANTHROPIC_API_KEY is required")
        if settings.database_url:
            pool = await asyncpg.create_pool(settings.database_url, min_size=2, max_size=10)
            app.state.db_pool = pool
            try:
                yield
            finally:
                await pool.close()
        else:
            yield

    app = FastAPI(
        title="Investor Intelligence API",
        version="0.1.0",
        docs_url="/",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.info(
            "http_exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
                "headers": redact_headers(dict(request.headers)),
                "request_id": request_id,
            },
        )
        body = ApiResponse[dict](
            success=False,
            request_id=request_id,
            error=ApiError(code="http_error", message=str(exc.detail)),
        )
        return JSONResponse(status_code=exc.status_code, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        body = ApiResponse[dict](
            success=False,
            request_id=request_id,
            error=ApiError(code="validation_error", message="invalid_request", details={"errors": exc.errors()}),
        )
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled_exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "request_id": request_id,
            },
        )
        body = ApiResponse[dict](
            success=False,
            request_id=request_id,
            error=ApiError(code="internal_error", message="internal server error"),
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    app.include_router(health_router)
    app.include_router(score_investors_router)
    app.include_router(analyze_signal_router)
    app.include_router(generate_digest_router)
    app.include_router(score_grants_router)
    app.include_router(benchmark_router)
    app.include_router(ingest_investor_router)

    return app


app = create_app()
