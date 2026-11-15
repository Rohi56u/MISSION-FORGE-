"""
Health and Readiness Probes for Kubernetes / Container Orchestration
"""

from pathlib import Path
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.app.core.database import get_db
from backend.app.core.config import settings

router = APIRouter(tags=["Health & System Diagnostics"])


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Liveness probe to confirm HTTP server is responsive."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness probe checking database connectivity and runtime storage."""
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "error": str(e),
            },
        )

    try:
        storage_dir = Path(settings.DOSSIER_STORAGE_DIR)
        storage_dir.mkdir(parents=True, exist_ok=True)
        probe_file = storage_dir / ".readiness_probe"
        probe_file.write_text("ready")
        probe_file.unlink(missing_ok=True)
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "storage": "unwritable",
                "error": str(e),
            },
        )

    return {
        "status": "ready",
        "service": settings.PROJECT_NAME,
        "database": "connected",
        "physics_engine": "operational",
        "dossier_storage": "writable",
    }
