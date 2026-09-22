# Multi-stage Dockerfile for AI Enhancement Service - Phase 5
FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /install /usr/local

COPY src/ ./ai/src/
COPY config/ ./ai/config/
COPY migrations/ ./ai/migrations/

ENV PYTHONUNBUFFERED=1
ENV AI_CONFIG_PATH=/app/ai/config/ai-config.yaml
ENV PYTHONPATH=/app

EXPOSE 8083

CMD ["python", "-m", "uvicorn", "ai.src.main:app", "--host", "0.0.0.0", "--port", "8083"]
