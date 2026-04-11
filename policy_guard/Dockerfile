# PolicyGuard V2 — Multi-stage Dockerfile
# Python 3.12-slim, non-root, production-ready

# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for some wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="Hunter Spence <hunter@hunterspence.dev>"
LABEL description="PolicyGuard V2 — Enterprise AI Governance & Compliance Platform"
LABEL version="2.0.0"

# Runtime system deps only (libpq for asyncpg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r policyguard && useradd -r -g policyguard -s /bin/false policyguard

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --chown=policyguard:policyguard . .

# Create directories for report output and logs
RUN mkdir -p /app/reports /app/logs \
    && chown -R policyguard:policyguard /app/reports /app/logs

USER policyguard

# Environment defaults (override at runtime)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    POLICYGUARD_ENV=production \
    POLICYGUARD_HOST=0.0.0.0 \
    POLICYGUARD_PORT=8080 \
    POLICYGUARD_WORKERS=2 \
    POLICYGUARD_LOG_LEVEL=info

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Default: run the FastAPI server via uvicorn
CMD ["python", "-m", "uvicorn", "api:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "2", \
     "--log-level", "info", \
     "--access-log"]
