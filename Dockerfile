# ==============================================================================
# VayuSutra APIx - Multi-Stage Enterprise Production Dockerfile
# Ministry of Statistics and Programme Implementation (MoSPI) / RBI / DGCA
# ==============================================================================

# Stage 1: Dependency Builder
FROM python:3.13-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Minimal Secure Runtime
FROM python:3.13-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    PYTHONPATH=/app \
    ENVIRONMENT=production

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user for security compliance (CIS Benchmark)
RUN groupadd -r mospi && useradd -r -g mospi -d /app -s /sbin/nologin -u 10001 mospi && \
    mkdir -p /app/vayusutra_apix/data /app/vayusutra_apix/static && \
    chown -R mospi:mospi /app

# Copy installed dependencies from builder
COPY --from=builder /install /usr/local

# Copy application source code
COPY --chown=mospi:mospi . /app

USER mospi

EXPOSE 8000

# Automated container healthcheck probing FastAPI health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["python3", "-m", "uvicorn", "vayusutra_apix.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-level", "info"]
