# AIAuditTrail V2 — Multi-stage Docker build
# Stage 1: builder (installs dependencies)
# Stage 2: runtime (minimal Python 3.12-slim, non-root user, health check)

# ---------------------------------------------------------------------------
# Stage 1: Build dependencies
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Security: non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy module code
COPY . .

# Data directory for SQLite audit DB
RUN mkdir -p /data && chown appuser:appgroup /data /app

USER appuser

# Environment defaults (override via docker-compose or -e flags)
ENV AUDIT_DB_PATH=/data/audit.db \
    AUDIT_PORT=8000 \
    AUDIT_DEV_MODE=false \
    AUDIT_STORE_PLAINTEXT=false \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

# Health check: hit the /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Start FastAPI server
CMD ["python", "-m", "uvicorn", "ai_audit_trail.api:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
