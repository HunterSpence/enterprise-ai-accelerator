# FinOps Intelligence V2 — Multi-stage Docker build
# Stage 1: build deps, Stage 2: slim runtime
#
# Build:  docker build -t finops-intelligence:v2 .
# Run:    docker run -p 8000:8000 finops-intelligence:v2
# Demo:   docker run --rm finops-intelligence:v2 python demo.py --fast

# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# System deps for duckdb, numpy, scikit-learn builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dep resolution
RUN pip install --no-cache-dir uv==0.4.29

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="FinOps Intelligence V2"
LABEL org.opencontainers.image.description="Enterprise cloud FinOps platform — $89,400/mo savings on $340K/mo spend"
LABEL org.opencontainers.image.version="2.0.0"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY . /app/finops_intelligence/

# Non-root user for security
RUN useradd -m -u 1001 finops && chown -R finops:finops /app
USER finops

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default: start API server
CMD ["uvicorn", "finops_intelligence.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
