# ==============================================================================
# Mission Forge Backend — Multi-Stage Production Dockerfile
# Stage 1: Build stage with compiler tools and package wheels
# Stage 2: Hardened, minimal, non-root runtime container
# ==============================================================================

# --- Stage 1: Builder ---
FROM python:3.12-slim-bookworm AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install build tools
RUN pip install --upgrade pip setuptools wheel

# Copy project specification files
COPY pyproject.toml requirements.txt .

# Install dependencies into wheel distribution / target directory
RUN pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.txt

# --- Stage 2: Production Runtime ---
FROM python:3.12-slim-bookworm AS runtime

# Security hardening: Create dedicated non-root application group and user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app -M appuser

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    DEBUG=false \
    PYTHONPATH=/app \
    DOSSIER_STORAGE_DIR=/app/artifacts/dossiers

# Install runtime system dependencies (curl for container healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels from builder stage and install
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Copy application source code, migrations, and configuration
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini
COPY pyproject.toml /app/pyproject.toml
COPY .flake8 /app/.flake8
COPY __init__.py /app/backend/__init__.py
COPY app /app/backend/app

# Create persistent storage directories with non-root ownership
RUN mkdir -p /app/artifacts/dossiers /app/data && \
    chown -R appuser:appgroup /app

# Switch to unprivileged non-root user
USER appuser:appgroup

# Expose internal API service port
EXPOSE 8000

# Container Liveness & Readiness Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production Entrypoint: Run with Uvicorn HTTP server
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--no-access-log"]
