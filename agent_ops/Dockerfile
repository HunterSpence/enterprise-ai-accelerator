# AgentOps — Multi-agent orchestration with OTEL tracing
# Python 3.12-slim, non-root, single-stage (no heavy build deps needed)

FROM python:3.12-slim

# Security: non-root user
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home --shell /sbin/nologin appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy module source
COPY --chown=appuser:appgroup . /app/agent_ops/

# Set PYTHONPATH so `import agent_ops` resolves from /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER appuser

EXPOSE 8006

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import agent_ops; print('ok')" || exit 1

# Default: run the demo (no persistent API server in this module)
CMD ["python", "-m", "agent_ops.demo"]
