"""
Mission Forge FastAPI Application Entry Point
"""

import logging
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.api.v1 import (
    health,
    physics,
    missions,
    components,
    horizons,
    dsn,
    techport,
    trajectory,
    auth,
    cdf,
    fdir,
    capcom,
    nasa,
    dossiers,
)

# Ensure all models are registered with Base.metadata before init_db
from backend.app.models import __all__ as _model_names

assert _model_names, "No SQLAlchemy models discovered in backend.app.models"


class SensitiveDataFilter(logging.Filter):
    """Redacts passwords, tokens, and secret keys from structured logs."""
    SENSITIVE_PATTERNS = [
        re.compile(r"(?i)(password|secret|token|api_key|authorization)[:=]\s*['\"]?([^'\"\s,]+)"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self.SENSITIVE_PATTERNS:
                record.msg = pattern.sub(r"\1: [REDACTED]", record.msg)
        return True


# Install logging redaction filter
logging.getLogger("uvicorn.access").addFilter(SensitiveDataFilter())
logging.getLogger("backend").addFilter(SensitiveDataFilter())


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    """Enforces maximum allowable HTTP request body size to mitigate DoS attacks."""
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
                    return Response(
                        content="Request payload exceeds maximum allowed size (10 MB).",
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize database and recover orphaned jobs; shutdown: cleanup HTTP clients."""
    await init_db()
    # Recover any orphaned background jobs left in QUEUED or RUNNING state from previous process run
    from backend.app.api.v1.trajectory import recover_orphaned_porkchop_jobs
    from backend.app.dossier.service import recover_orphaned_dossier_jobs, get_storage_dir
    from backend.app.core.database import AsyncSessionLocal

    get_storage_dir()
    async with AsyncSessionLocal() as session:
        await recover_orphaned_porkchop_jobs(session)
        await recover_orphaned_dossier_jobs(session)

    yield
    # Graceful resource cleanup for external aerospace API clients and pub/sub
    from backend.app.integrations.horizons import horizons_client
    from backend.app.integrations.dsn import dsn_client
    from backend.app.integrations.techport import techport_client
    from backend.app.integrations.nasa import nasa_api_client
    from backend.app.cdf.broadcast import broadcast_backend

    await horizons_client.aclose()
    await dsn_client.aclose()
    await techport_client.aclose()
    await nasa_api_client.aclose()
    await broadcast_backend.close()


app = FastAPI(
    title="Mission Forge API",
    version="1.0.0",
    description=(
        "Production-grade aerospace mission-design & collaborative simulation "
        "platform for NASA Space Apps 2026."
    ),
    lifespan=lifespan,
)

# Explicit, secure CORS configuration with credential protection
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
    expose_headers=settings.CORS_EXPOSE_HEADERS,
    max_age=settings.CORS_MAX_AGE,
)
app.add_middleware(PayloadSizeLimitMiddleware)

# Register API v1 routers
app.include_router(health.router, tags=["health"])
app.include_router(physics.router, prefix="/api/v1", tags=["physics"])
app.include_router(missions.router, prefix="/api/v1", tags=["missions"])
app.include_router(components.router, prefix="/api/v1", tags=["components"])
app.include_router(horizons.router, prefix="/api/v1", tags=["horizons"])
app.include_router(dsn.router, prefix="/api/v1", tags=["dsn"])
app.include_router(techport.router, prefix="/api/v1", tags=["techport"])
app.include_router(trajectory.router, prefix="/api/v1", tags=["trajectory"])
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(cdf.router, prefix="/api/v1", tags=["cdf"])
app.include_router(fdir.router, prefix="/api/v1", tags=["fdir"])
app.include_router(capcom.router, prefix="/api/v1", tags=["capcom"])
app.include_router(nasa.router, prefix="/api/v1", tags=["nasa"])
app.include_router(dossiers.router, prefix="/api/v1", tags=["dossiers"])

# Ensure all registered routes (including WebSocket routes) expose .methods attribute
# for consistent route introspection and test tooling compatibility
for route in app.routes:
    if not hasattr(route, "methods"):
        setattr(route, "methods", None)
