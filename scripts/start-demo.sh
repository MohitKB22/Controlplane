#!/bin/sh
# Entrypoint for the single-container demo image (root Dockerfile).
#
#   1. apply migrations
#   2. load demo data (idempotent — safe on every start)
#   3. serve API + web app on $PORT
#
# Set SEED_ON_START=false to skip step 2.
set -eu

echo "==> Applying database migrations"
alembic upgrade head

if [ "${DEMO_MODE:-true}" = "true" ] && [ "${SEED_ON_START:-true}" = "true" ]; then
  echo "==> Loading demo data"
  python -m app.db.seed
fi

echo "==> Starting the API on port ${PORT:-8000}"
# --proxy-headers: behind a hosting proxy (Render, Container Apps), take the
# client address from X-Forwarded-For so per-client rate limits are per client,
# not one shared bucket for every anonymous visitor.
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "*"
