# Multi-stage Dockerfile for Correlation Engine - Phase 3
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY migrations/ ./migrations/

# Environment
ENV PYTHONUNBUFFERED=1
ENV CORRELATION_CONFIG_PATH=/app/config/correlation-config.yaml

EXPOSE 8081

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8081"]
