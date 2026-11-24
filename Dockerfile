# syntax=docker/dockerfile:1
#
# Single-container demo image: the API serves the built web app on the same
# origin, so the browser needs no CORS configuration and one service is enough
# (used for the hosted Render demo — see render.yaml and docs/DEPLOYMENT.md).
#
# The per-app images in apps/api and apps/web remain the production path.

# ------------------------------------------------------------------ web build
FROM node:20-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
# Empty base URL: the UI calls /api/v1 on whatever origin served it.
ENV VITE_API_BASE_URL=""
RUN npm run build

# -------------------------------------------------------------------- runtime
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/api/pyproject.toml ./
COPY apps/api/app ./app
RUN pip install --no-cache-dir .

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY scripts/start-demo.sh ./start-demo.sh
COPY --from=web /web/dist ./web

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/var/blobs \
    && chmod +x /app/start-demo.sh \
    && chown -R appuser:appuser /app
USER appuser

# Defaults for a self-contained demo. Every one can be overridden at deploy
# time; point DATABASE_URL at PostgreSQL for data that must survive restarts.
ENV ENVIRONMENT=dev \
    DEMO_MODE=true \
    WEB_DIST_DIR=/app/web \
    DATABASE_URL=sqlite:////app/data/aicc.db \
    LOCAL_BLOB_DIR=/app/var/blobs \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health/live').status==200 else 1)"

CMD ["./start-demo.sh"]
