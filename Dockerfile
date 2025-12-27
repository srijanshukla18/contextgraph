FROM python:3.12-slim

WORKDIR /app

# Install postgres client for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY sdk/python/pyproject.toml sdk/python/README.md sdk/python/
RUN pip install --no-cache-dir -e sdk/python[server]

# Copy application code
COPY sdk/python/contextgraph sdk/python/contextgraph
COPY server server
COPY storage storage

ENV DATABASE_URL=postgresql://postgres:postgres@db:5432/contextgraph

EXPOSE 8080

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
