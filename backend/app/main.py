from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import router
from app.core.config import get_settings
from app.core.middleware import RequestContextMiddleware
from app.persistence.database import get_engine

settings = get_settings()
settings.validate_runtime()
logging.basicConfig(level=logging.INFO, format="%(message)s")

app = FastAPI(
    title="sl3dge API",
    version="0.1.0",
    description="Verification-first financial control engine",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.parsed_trusted_hosts)
if settings.force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(router)


@app.get("/health/live", include_in_schema=False)
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready", include_in_schema=False)
def readiness() -> dict[str, str]:
    engine = get_engine()
    if engine is None:
        if settings.environment in {"staging", "production"}:
            raise HTTPException(status_code=503, detail="Database is not configured")
        return {"status": "ready", "database": "in-memory-development"}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready", "database": "postgres"}


@app.exception_handler(ValueError)
async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": str(exc),
                "details": {},
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, _: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logging.getLogger("sl3dge.error").exception(
        "Unhandled request failure request_id=%s path=%s", request_id, request.url.path
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "The request could not be completed",
                "request_id": request_id,
            }
        },
    )
