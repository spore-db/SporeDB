# Stage 1: Builder
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[cloud]"

# Stage 2: Runtime
FROM python:3.12-slim

LABEL org.opencontainers.image.title="SporeDB"
LABEL org.opencontainers.image.description="Bioprocess-native time-series database"
LABEL org.opencontainers.image.url="https://github.com/spore-db/SporeDB"
LABEL org.opencontainers.image.source="https://github.com/spore-db/SporeDB"
LABEL org.opencontainers.image.version="0.1.0"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL org.opencontainers.image.vendor="SporeDB Contributors"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create non-root user
RUN useradd --create-home sporedb

WORKDIR /home/sporedb/app

COPY src/ src/
COPY README.md .

# Create keys directory owned by sporedb user
RUN mkdir -p keys && chown -R sporedb:sporedb /home/sporedb

USER sporedb

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["uvicorn", "sporedb.cloud.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
