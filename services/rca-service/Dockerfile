# Multi-stage Dockerfile for RCA Service - Phase 4
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
ENV RCA_CONFIG_PATH=/app/config/rca-config.yaml

EXPOSE 8082

CMD ["python", "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8082"]
