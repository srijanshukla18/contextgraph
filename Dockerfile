FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY sdk/python/pyproject.toml sdk/python/README.md sdk/python/
RUN pip install --no-cache-dir -e sdk/python[server]

# Production stage
FROM python:3.12-slim

# Create non-root user
RUN groupadd --gid 1000 contextgraph \
    && useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home contextgraph

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=contextgraph:contextgraph sdk/python/contextgraph sdk/python/contextgraph
COPY --chown=contextgraph:contextgraph server server
COPY --chown=contextgraph:contextgraph storage storage

# Switch to non-root user
USER contextgraph

# Environment variables (no defaults for secrets)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
