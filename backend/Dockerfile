# Multi-stage image (Phase 3, D-70).
#   target "api"    : the web API. Development image (uvicorn --reload, test and lint tools). NO document parsers.
#   target "worker" : the Celery worker/beat. Adds Tesseract and the parsing libraries, runs as a non-root user.
# A production image should install requirements.txt only (api) or requirements-worker.txt (worker).

FROM python:3.12-slim AS base
WORKDIR /app
# System deps for psycopg (PostgreSQL client)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

FROM base AS api
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS worker
# OCR engine and English data. More languages: add tesseract-ocr-<lang> packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-worker.txt ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements-worker.txt
COPY . .
# Non-root; the root filesystem is read-only in compose with a tmpfs scratch dir.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin worker
USER worker
ENV TMPDIR=/scratch HOME=/scratch PYTHONDONTWRITEBYTECODE=1
CMD ["celery", "-A", "app.ingestion.worker:celery_app", "worker", "--loglevel=INFO", "--concurrency=2"]
