# =============================================================================
# CloudIQ V2 — Multi-stage Dockerfile
# Stage 1: builder — installs all dependencies in a venv
# Stage 2: runtime — copies only the venv + source, runs as non-root
# =============================================================================

# ---- Builder ----------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build tools needed for scikit-learn / numpy compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libgomp1 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements_v2.txt .
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip==24.0 && \
    /venv/bin/pip install --no-cache-dir -r requirements_v2.txt


# ---- Runtime ----------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Security: run as non-root user
RUN groupadd -r cloudiq && useradd -r -g cloudiq cloudiq

WORKDIR /app

# Copy venv from builder — no build tools in runtime image
COPY --from=builder /venv /venv
ENV PATH="/venv/bin:$PATH"

# Copy application source
COPY . .

# Drop write access to source after copying
RUN chown -R cloudiq:cloudiq /app && chmod -R 555 /app

USER cloudiq

# Expose FastAPI port
EXPOSE 8080

# Health check — hits /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Default command: run FastAPI with uvicorn
CMD ["uvicorn", "cloud_iq.api:app", "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "2", "--log-level", "info"]
