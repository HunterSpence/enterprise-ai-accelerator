# ─── MigrationScout V2 — Multi-stage Docker build ────────────────────────────
# Stage 1: Build dependencies in a full image
# Stage 2: Lean runtime image (non-root, health check, minimal surface area)
#
# Build:
#   docker build -t migration-scout:v2 .
#
# Run API:
#   docker run -p 8080:8080 -e ANTHROPIC_API_KEY=sk-ant-... migration-scout:v2
#
# Run demo (no API key needed):
#   docker run --rm migration-scout:v2 python -m migration_scout.demo --no-ai

# ─── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for numpy/scikit-learn wheel compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first for layer caching
COPY requirements.txt ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid 1001 --no-create-home --shell /bin/bash appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=appuser:appgroup . /app/migration_scout/

# Set Python path so `import migration_scout` works
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # API defaults (override at runtime)
    HOST=0.0.0.0 \
    PORT=8080 \
    LOG_LEVEL=info

USER appuser

EXPOSE 8080

# Health check: poll /health every 30s, 3 retries, 10s start period
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Default: start FastAPI server
CMD ["python", "-m", "uvicorn", "migration_scout.api:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--log-level", "info", "--workers", "1"]
