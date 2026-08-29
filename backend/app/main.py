from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
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
REQUIRED_SCHEMA_REVISION = "0016_control_proposal_validation"

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
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
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
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    if revision != REQUIRED_SCHEMA_REVISION:
        raise HTTPException(status_code=503, detail="Database schema is not current")
    return {"status": "ready", "database": "postgres"}


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "INVALID_INPUT",
                "message": str(exc),
                "details": {},
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    code = {
        400: "BAD_REQUEST",
        401: "AUTHENTICATION_REQUIRED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        413: "PAYLOAD_TOO_LARGE",
        422: "INVALID_INPUT",
        428: "PRECONDITION_REQUIRED",
        429: "RATE_LIMITED",
        503: "DEPENDENCY_UNAVAILABLE",
    }.get(exc.status_code, "REQUEST_FAILED")
    details = exc.detail if isinstance(exc.detail, dict) else {}
    message = (
        str(exc.detail.get("message", code))
        if isinstance(exc.detail, dict)
        else str(exc.detail or code)
    )
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    details = [
        {
            "location": [str(part) for part in item["loc"]],
            "message": item["msg"],
            "type": item["type"],
        }
        for item in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "The request payload is invalid",
                "details": details,
                "request_id": request_id,
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
                "details": {},
                "request_id": request_id,
            }
        },
    )
