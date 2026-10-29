#!/bin/sh
# Backend container entrypoint.
#
# 1. Wait for Postgres to accept connections (compose healthcheck also gates
#    this, but we double-check so migrations never race a half-ready DB).
# 2. Run Alembic migrations to create/upgrade the schema.
# 3. Start uvicorn.
#
# Any failure in migration aborts startup (set -e) so we never serve against
# an out-of-date schema.
#
# PORT: Railway (and most PaaS hosts) inject a $PORT the app must bind. We use
# it when present and fall back to 8000 so local `docker compose` is unchanged.

set -e

echo "[entrypoint] running database migrations..."
alembic upgrade head

echo "[entrypoint] starting uvicorn on port ${PORT:-8000}..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"